//! Bounded background expert reads, consumed only after actual routing.
//! No cache/history mutation. Dropping a pending request drains its I/O before
//! its buffers return to the scratch pool, including on unwind or misprediction.
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{sync_channel, Receiver, SyncSender};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread::JoinHandle;

use super::read_buffers::{ReadBuffer, ReadBuffers};

#[derive(Default, Debug, serde::Serialize)]
pub struct PredictionReadStats {
    pub scheduled: u64,
    pub successful: u64,
    pub useful: u64,
    pub unused: u64,
    pub read_failures: u64,
    pub worker_failures: u64,
    pub dispatch_failures: u64,
    pub useful_bytes: u64,
    pub unused_bytes: u64,
}

#[derive(Default)]
struct Counters {
    scheduled: AtomicU64,
    successful: AtomicU64,
    useful: AtomicU64,
    unused: AtomicU64,
    read_failures: AtomicU64,
    worker_failures: AtomicU64,
    dispatch_failures: AtomicU64,
    useful_bytes: AtomicU64,
    unused_bytes: AtomicU64,
}

impl Counters {
    fn snapshot(&self) -> PredictionReadStats {
        PredictionReadStats {
            scheduled: self.scheduled.load(Ordering::Relaxed),
            successful: self.successful.load(Ordering::Relaxed),
            useful: self.useful.load(Ordering::Relaxed),
            unused: self.unused.load(Ordering::Relaxed),
            read_failures: self.read_failures.load(Ordering::Relaxed),
            worker_failures: self.worker_failures.load(Ordering::Relaxed),
            dispatch_failures: self.dispatch_failures.load(Ordering::Relaxed),
            useful_bytes: self.useful_bytes.load(Ordering::Relaxed),
            unused_bytes: self.unused_bytes.load(Ordering::Relaxed),
        }
    }
}

struct Outcome {
    buffers: ReadBuffers,
    complete: bool,
}

struct Request {
    path: PathBuf,
    length: usize,
    response: SyncSender<Outcome>,
    buffers: ReadBuffers,
}

struct Reader {
    sender: Option<SyncSender<Request>>,
    thread: Option<JoinHandle<()>>,
    counters: Arc<Counters>,
}

impl Reader {
    fn new() -> io::Result<Self> {
        Self::with_read_fn(|buffer, path, length| buffer.read(path, length))
    }

    fn with_read_fn(
        mut read: impl FnMut(&mut ReadBuffer, &Path, usize) -> io::Result<()> + Send + 'static,
    ) -> io::Result<Self> {
        // Two queued requests let a model submit current + next without waiting
        // for worker dispatch. One independent worker avoids Rayon starvation.
        let (sender, requests) = sync_channel::<Request>(2);
        let counters = Arc::new(Counters::default());
        let counts = counters.clone();
        let thread = std::thread::Builder::new()
            .name("inkling-predicted-read".into())
            .spawn(move || {
                while let Ok(mut request) = requests.recv() {
                    let complete = read(
                        &mut request.buffers.buffers[0],
                        &request.path,
                        request.length,
                    )
                    .is_ok();
                    if complete {
                        counts.successful.fetch_add(1, Ordering::Relaxed);
                    } else {
                        counts.read_failures.fetch_add(1, Ordering::Relaxed);
                    }
                    // Capacity one allows completion even if the owner is
                    // still computing attention or unwinding another branch.
                    let _ = request.response.send(Outcome {
                        buffers: request.buffers,
                        complete,
                    });
                }
            })?;
        Ok(Self {
            sender: Some(sender),
            thread: Some(thread),
            counters,
        })
    }

    fn start(&self, expert: usize, path: &Path, length: usize) -> Option<PendingRead> {
        let (response, receiver) = sync_channel(1);
        let request = Request {
            path: path.to_owned(),
            length,
            response,
            buffers: ReadBuffers::acquire(1),
        };
        if self.sender.as_ref()?.send(request).is_err() {
            self.counters
                .dispatch_failures
                .fetch_add(1, Ordering::Relaxed);
            return None;
        }
        self.counters.scheduled.fetch_add(1, Ordering::Relaxed);
        Some(PendingRead {
            expert,
            receiver: Mutex::new(Some(receiver)),
            counters: self.counters.clone(),
        })
    }
}

impl Drop for Reader {
    fn drop(&mut self) {
        drop(self.sender.take());
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

static READER: OnceLock<Option<Reader>> = OnceLock::new();
static SECOND_READER: OnceLock<Option<Reader>> = OnceLock::new();

fn parse_second_rank(raw: Option<&str>) -> usize {
    raw.and_then(|value| value.parse::<usize>().ok())
        .filter(|value| (1..=5).contains(value))
        .unwrap_or(2)
}

/// Original predicted gate rank, zero based. Default2 retains the qualified
/// top-three policy; the experiment changes selection only, never read bounds.
pub fn second_prediction_rank_ceiling() -> usize {
    static CEILING: OnceLock<usize> = OnceLock::new();
    *CEILING.get_or_init(|| {
        parse_second_rank(
            std::env::var("CASCADIA_INKLING_SECOND_PREDICT_RANK")
                .ok()
                .as_deref(),
        )
    })
}

pub(super) fn second_reads_requested() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    // Early mode already overlaps two layers. It takes precedence so combining
    // flags cannot expand the bound beyond two live predicted reads.
    !early_reads_requested()
        && *ENABLED.get_or_init(|| super::env_flag("CASCADIA_INKLING_SECOND_PREDICT_READS"))
}

pub fn second_prediction_read_statistics() -> PredictionReadStats {
    SECOND_READER
        .get()
        .and_then(Option::as_ref)
        .map(|reader| reader.counters.snapshot())
        .unwrap_or_default()
}

pub fn prediction_read_worker_count() -> usize {
    [&READER, &SECOND_READER]
        .iter()
        .filter(|reader| reader.get().and_then(Option::as_ref).is_some())
        .count()
}

pub(super) fn early_reads_requested() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| super::env_flag("CASCADIA_INKLING_EARLY_PREDICT_READS"))
}

pub fn prediction_read_statistics() -> PredictionReadStats {
    let mut total = READER
        .get()
        .and_then(Option::as_ref)
        .map(|reader| reader.counters.snapshot())
        .unwrap_or_default();
    let second = second_prediction_read_statistics();
    total.scheduled += second.scheduled;
    total.successful += second.successful;
    total.useful += second.useful;
    total.unused += second.unused;
    total.read_failures += second.read_failures;
    total.worker_failures += second.worker_failures;
    total.dispatch_failures += second.dispatch_failures;
    total.useful_bytes += second.useful_bytes;
    total.unused_bytes += second.unused_bytes;
    total
}

pub(super) fn start(expert: usize, path: &Path, length: usize) -> Option<PendingRead> {
    READER
        .get_or_init(|| Reader::new().ok())
        .as_ref()?
        .start(expert, path, length)
}

pub(super) fn start_second(expert: usize, path: &Path, length: usize) -> Option<PendingRead> {
    SECOND_READER
        .get_or_init(|| Reader::new().ok())
        .as_ref()?
        .start(expert, path, length)
}

/// At most two independent, complete expert reads for the current layer.
/// Each request retains its own expert identity and drains on drop.
pub(super) struct PendingReadGroup {
    requests: [Option<PendingRead>; 2],
}

impl PendingReadGroup {
    pub fn new(first: Option<PendingRead>, second: Option<PendingRead>) -> Option<Self> {
        if first.is_none() && second.is_none() {
            return None;
        }
        Some(Self {
            requests: [first, second],
        })
    }

    pub fn take_for(&self, expert: usize, destination: &mut ReadBuffer) -> bool {
        self.requests
            .iter()
            .flatten()
            .find(|request| request.expert == expert)
            .is_some_and(|request| request.take_for(expert, destination))
    }
}

pub(super) struct PendingRead {
    expert: usize,
    receiver: Mutex<Option<Receiver<Outcome>>>,
    counters: Arc<Counters>,
}

impl PendingRead {
    fn receive(&self) -> Option<Outcome> {
        let receiver = self
            .receiver
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .take()?;
        match receiver.recv() {
            Ok(outcome) => Some(outcome),
            Err(_) => {
                self.counters
                    .worker_failures
                    .fetch_add(1, Ordering::Relaxed);
                None
            }
        }
    }

    /// Only the actual selected expert may consume this request. Transfer the
    /// allocation into its normal scratch slot; admission stays in gate order.
    pub fn take_for(&self, expert: usize, destination: &mut ReadBuffer) -> bool {
        if expert != self.expert {
            return false;
        }
        let Some(mut outcome) = self.receive() else {
            return false;
        };
        if !outcome.complete {
            return false;
        }
        let bytes = outcome.buffers.buffers[0].as_slice().len();
        std::mem::swap(destination, &mut outcome.buffers.buffers[0]);
        self.counters.useful.fetch_add(1, Ordering::Relaxed);
        self.counters
            .useful_bytes
            .fetch_add(bytes as u64, Ordering::Relaxed);
        true
    }
}

impl Drop for PendingRead {
    fn drop(&mut self) {
        if let Some(outcome) = self.receive() {
            if outcome.complete {
                self.counters.unused.fetch_add(1, Ordering::Relaxed);
                self.counters.unused_bytes.fetch_add(
                    outcome.buffers.buffers[0].as_slice().len() as u64,
                    Ordering::Relaxed,
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn rank_configuration_is_bounded_and_defaults_to_qualified_policy() {
        for rank in 1..=5 {
            assert_eq!(parse_second_rank(Some(&rank.to_string())), rank);
        }
        for raw in [
            None,
            Some(""),
            Some("0"),
            Some("6"),
            Some("-1"),
            Some("bad"),
            Some("9999999999999999999999999999"),
        ] {
            assert_eq!(parse_second_rank(raw), 2);
        }
    }

    #[test]
    fn two_workers_start_concurrently_and_keep_expert_buffers_distinct() {
        let mut files = [
            tempfile::NamedTempFile::new().unwrap(),
            tempfile::NamedTempFile::new().unwrap(),
        ];
        files[0].write_all(&[17; 4096]).unwrap();
        files[1].write_all(&[93; 4096]).unwrap();
        let (entered, arrived) = sync_channel(2);
        let mut releases = Vec::new();
        let readers: Vec<_> = (0..2)
            .map(|index| {
                let entered = entered.clone();
                let (release, wait) = sync_channel(1);
                releases.push(release);
                Reader::with_read_fn(move |buffer, path, length| {
                    entered.send(index).unwrap();
                    wait.recv().unwrap();
                    buffer.read(path, length)
                })
                .unwrap()
            })
            .collect();
        let group = PendingReadGroup::new(
            readers[0].start(3, files[0].path(), 4096),
            readers[1].start(7, files[1].path(), 4096),
        )
        .unwrap();
        let timeout = std::time::Duration::from_secs(5);
        let first = arrived.recv_timeout(timeout);
        let second = arrived.recv_timeout(timeout);
        // Always release before asserting so failure cannot hang RAII cleanup.
        for release in releases {
            release.send(()).unwrap();
        }
        assert_ne!(first.unwrap(), second.unwrap());
        let mut destinations = [ReadBuffer::default(), ReadBuffer::default()];
        assert!(!group.take_for(4, &mut destinations[0]));
        // Consume in the reverse order of prediction; routing controls identity.
        assert!(group.take_for(7, &mut destinations[1]));
        assert!(group.take_for(3, &mut destinations[0]));
        assert_eq!(destinations[0].as_slice(), [17; 4096]);
        assert_eq!(destinations[1].as_slice(), [93; 4096]);
        assert!(!group.take_for(7, &mut destinations[0]));
        drop(group);
        for reader in readers {
            let stats = reader.counters.snapshot();
            assert_eq!(
                (
                    stats.scheduled,
                    stats.successful,
                    stats.useful,
                    stats.unused
                ),
                (1, 1, 1, 0)
            );
            assert_eq!(stats.useful_bytes, 4096);
        }
    }

    #[test]
    fn only_matching_expert_consumes_complete_bytes_once() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        file.write_all(&[17; 4096]).unwrap();
        let reader = Reader::new().unwrap();
        let request = reader.start(3, file.path(), 4096).unwrap();
        let mut destination = ReadBuffer::default();
        assert!(!request.take_for(2, &mut destination));
        assert!(destination.as_slice().is_empty());
        assert!(request.take_for(3, &mut destination));
        assert_eq!(destination.as_slice(), [17; 4096]);
        assert!(!request.take_for(3, &mut destination));
        drop(request);
        let stats = reader.counters.snapshot();
        assert_eq!(
            (
                stats.scheduled,
                stats.successful,
                stats.useful,
                stats.unused
            ),
            (1, 1, 1, 0)
        );
        assert_eq!(stats.useful_bytes, 4096);
    }

    #[test]
    fn failed_prediction_leaves_destination_intact_and_worker_can_continue() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        file.write_all(&[93; 4096]).unwrap();
        let reader = Reader::new().unwrap();
        let mut destination = ReadBuffer::default();
        destination.read(file.path(), 4096).unwrap();
        let request = reader.start(3, file.path(), 8192).unwrap();
        assert!(!request.take_for(3, &mut destination));
        assert_eq!(destination.as_slice(), [93; 4096]);
        drop(request);
        drop(reader.start(4, file.path(), 4096).unwrap());
        let stats = reader.counters.snapshot();
        assert_eq!(
            (stats.scheduled, stats.read_failures, stats.unused),
            (2, 1, 1)
        );
        assert_eq!(stats.unused_bytes, 4096);
    }

    #[test]
    fn unused_drop_drains_in_flight_read_before_returning() {
        let (entered, arrived) = sync_channel(1);
        let (release, wait) = sync_channel(1);
        let reader = Reader::with_read_fn(move |_, _, _| {
            entered.send(()).unwrap();
            wait.recv().unwrap();
            Err(io::Error::other("injected read failure"))
        })
        .unwrap();
        let request = reader.start(0, Path::new("unused"), 4096).unwrap();
        arrived.recv().unwrap();
        let (finished, done) = sync_channel(1);
        let thread = std::thread::spawn(move || {
            drop(request);
            finished.send(()).unwrap();
        });
        assert!(done.try_recv().is_err());
        release.send(()).unwrap();
        done.recv().unwrap();
        thread.join().unwrap();
        assert_eq!(reader.counters.snapshot().read_failures, 1);
    }

    #[test]
    fn blocked_worker_accepts_two_queued_requests_without_losing_ownership() {
        let (entered, arrived) = sync_channel(1);
        let (release, wait) = sync_channel(1);
        let mut first = true;
        let reader = Reader::with_read_fn(move |_, _, _| {
            if first {
                first = false;
                entered.send(()).unwrap();
                wait.recv().unwrap();
            }
            Err(io::Error::other("injected failure"))
        })
        .unwrap();
        let active = reader.start(0, Path::new("first"), 4096).unwrap();
        arrived.recv().unwrap();
        let (queued, received) = sync_channel(1);
        let thread = std::thread::spawn(move || {
            let second = reader.start(1, Path::new("second"), 4096).unwrap();
            let third = reader.start(2, Path::new("third"), 4096).unwrap();
            queued.send(()).unwrap();
            drop(second);
            drop(third);
            reader
        });
        let accepted = received.recv_timeout(std::time::Duration::from_secs(5));
        // Release even on test failure, so a queue-size regression cannot hang.
        release.send(()).unwrap();
        drop(active);
        let reader = thread.join().unwrap();
        assert!(accepted.is_ok(), "queued submission blocked on file I/O");
        let stats = reader.counters.snapshot();
        assert_eq!(
            (
                stats.scheduled,
                stats.read_failures,
                stats.dispatch_failures
            ),
            (3, 3, 0)
        );
    }

    #[test]
    fn disconnected_worker_falls_back_without_exposing_bytes_or_hanging() {
        let mut reader = Reader::with_read_fn(|_, _, _| panic!("injected worker panic")).unwrap();
        let request = reader.start(0, Path::new("unused"), 4096).unwrap();
        let mut destination = ReadBuffer::default();
        assert!(!request.take_for(0, &mut destination));
        drop(request);
        assert!(destination.as_slice().is_empty());
        assert!(reader.thread.take().unwrap().join().is_err());
        assert!(reader.start(1, Path::new("unused"), 4096).is_none());
        let stats = reader.counters.snapshot();
        assert_eq!((stats.worker_failures, stats.dispatch_failures), (1, 1));
    }
}
