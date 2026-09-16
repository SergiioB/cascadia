//! The driver's reply-timeout path: when one worker never answers, the
//! dispatch fails and that connection is dropped so a late reply cannot be
//! misread as the next layer's, while healthy workers stay usable. This runs
//! in its own test binary because it lowers the process-global activation
//! timeout via `set_activation_timeout_secs`.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use cascadia_engine::Engine;
use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::ep::{load_expert_bank, EpClient, ExpertWorkerEngine};
use cascadia_engine_sparse_moe::inkling::loader::read_manifest;
use cascadia_transport::{set_activation_timeout_secs, ActivationClient, ActivationServer};
use tokio::sync::Mutex;

fn export_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/inkling_export")
}

fn runtime() -> tokio::runtime::Runtime {
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap()
}

/// One accepted loopback pair: (worker-side server, driver-side client).
async fn loopback() -> (Arc<Mutex<ActivationServer>>, Arc<Mutex<ActivationClient>>) {
    let mut server = ActivationServer::new("127.0.0.1", 0);
    server.start().await.unwrap();
    let port = server.port();
    let server = Arc::new(Mutex::new(server));
    let sc = server.clone();
    let accept = tokio::spawn(async move { sc.lock().await.accept().await.unwrap() });
    let mut client = ActivationClient::new("127.0.0.1", port);
    client
        .connect_with_timeout(Duration::from_secs(5))
        .await
        .unwrap();
    accept.await.unwrap();
    (server, Arc::new(Mutex::new(client)))
}

#[test]
fn a_dead_worker_times_out_drops_its_connection_and_leaves_survivors_usable() {
    let dir = export_dir();
    let m = read_manifest(&dir).expect("checked-in inkling_export manifest");
    let rt = runtime();
    let hs = m.hidden_size;
    let li = (0..m.num_layers)
        .find(|li| !m.dense_layers.contains(li))
        .expect("a MoE layer");

    // Bound the driver's owed-reply wait to ~1s so the black-hole worker times
    // out quickly. Idle worker recvs are exempt from this timeout, so worker 0
    // is unaffected between dispatches.
    set_activation_timeout_secs(1);

    // Worker 0 is a live shard 0 of 2 (owns even ids). Worker 1 is a black hole:
    // its server accepts the connection but never reads or replies, so any frame
    // homed to it (an odd id under W=2) never gets an answer.
    let (s0, c0) = rt.block_on(loopback());
    let (_black_hole_server, c1) = rt.block_on(loopback());
    let w0 = load_expert_bank(&dir, 0, 2, ExpertsMode::Eager).unwrap();
    let owned0 = w0.owned_ids(li);
    let mut engine = ExpertWorkerEngine::new(w0, s0, rt.handle().clone());
    let worker0 = std::thread::spawn(move || loop {
        match engine.step() {
            Ok(_) => {}
            Err(e) if e.is_connection_fatal() => break,
            Err(e) => panic!("worker 0 step: {e}"),
        }
    });

    let ep = EpClient::new(
        vec![c0.clone(), c1.clone()],
        rt.handle().clone(),
        hs,
        m.num_experts,
        m.n_shared_experts,
    );
    assert_eq!(ep.n_workers(), 2);
    let even = *owned0.iter().find(|&&id| id % 2 == 0).expect("an even id");
    let odd = (0..m.num_experts)
        .find(|id| id % 2 == 1)
        .expect("an odd id");
    let x: Vec<f32> = (0..hs).map(|i| ((i % 5) as f32 - 2.0) * 0.1).collect();

    // The odd id homes to the black-hole worker 1, which never replies: the
    // dispatch fails with the timeout error, and worker 1's connection is
    // dropped so a late reply cannot be read as the next layer's.
    let err = ep
        .dispatch(li as u32, &x, &[vec![(even, 0.5), (odd, 0.25)]])
        .expect_err("a dead worker must fail the dispatch");
    assert!(
        err.contains("no result within") && err.contains("connection dropped"),
        "expected a reply-timeout error, got: {err}"
    );

    // Worker 0's connection was never touched by the timeout: a dispatch that
    // involves only worker 0 still succeeds and equals local accumulation.
    let got = ep
        .dispatch(li as u32, &x, &[vec![(even, 0.5)]])
        .expect("the surviving worker still serves after a peer timeout");
    let y = load_expert_bank(&dir, 0, 2, ExpertsMode::Eager)
        .unwrap()
        .expert(li, even)
        .unwrap()
        .forward(&x, hs, m.moe_intermediate);
    let want: Vec<f32> = y.iter().map(|&yi| 0.5 * yi).collect();
    assert_eq!(got, want);

    drop(ep);
    rt.block_on(async {
        c0.lock().await.close().await;
    });
    worker0.join().unwrap();
}
