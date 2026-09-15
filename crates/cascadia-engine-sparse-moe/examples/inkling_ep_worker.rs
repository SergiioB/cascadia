//! Standalone EP benchmark worker. Production serving also exposes these roles
//! through `cascadia worker --ep-worker-index/--ep-worker-count`.
//! --export DIR --listen IP:PORT --index N --count W [--placement FILE]
//! Exits on driver disconnect; no tokenizer, API, or attention weights.

use cascadia_engine::Engine;
use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::ep::{
    load_expert_bank_with_placement, ExpertWorkerEngine,
};
use cascadia_engine_sparse_moe::inkling::ep_placement::EpPlacement;
use cascadia_engine_sparse_moe::inkling::loader::read_manifest;
use cascadia_transport::ActivationServer;
use std::{path::PathBuf, sync::Arc};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (mut export, mut listen, mut index, mut count, mut placement) =
        (None, None, None, None, None);
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or("each flag requires a value")?;
        match flag.as_str() {
            "--export" => export = Some(PathBuf::from(value)),
            "--listen" => listen = Some(value.parse::<std::net::SocketAddr>()?),
            "--index" => index = Some(value.parse::<u32>()?),
            "--count" => count = Some(value.parse::<u32>()?),
            "--placement" => placement = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown flag {flag}").into()),
        }
    }
    let export = export.ok_or("--export required")?;
    let listen = listen.ok_or("--listen required")?;
    let index = index.ok_or("--index required")?;
    let count = count.ok_or("--count required")?;
    let m = read_manifest(&export)?;
    let plan = placement
        .map(|p| EpPlacement::read(&p, &m, count as usize))
        .transpose()?;
    let bank =
        load_expert_bank_with_placement(&export, index, count, ExpertsMode::Mmap, plan.as_ref())?;
    println!(
        "bank_loaded index={index} count={count} experts={}",
        bank.n_experts()
    );
    println!("backend_start={}", bank.backend_stats());
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let mut server = ActivationServer::new(listen.ip().to_string(), listen.port());
    rt.block_on(server.start())?;
    println!("listening={listen}");
    rt.block_on(server.accept())?;
    let mut engine = ExpertWorkerEngine::new(
        bank,
        Arc::new(tokio::sync::Mutex::new(server)),
        rt.handle().clone(),
    );
    engine.warmup();
    loop {
        match engine.step() {
            Ok(_) => (),
            Err(e) if e.is_connection_fatal() => break,
            Err(e) => return Err(e.into()),
        }
    }
    println!("frames_served={}", engine.frames_served());
    println!("backend_final={}", engine.bank().backend_stats());
    engine.close();
    Ok(())
}
