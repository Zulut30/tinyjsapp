#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[tauri::command]
fn challenge() -> Result<serde_json::Value, String> {
    let nonce = std::env::var("TINYJS_BENCH_NONCE").map_err(|e| e.to_string())?;
    Ok(serde_json::json!({"nonce": nonce, "values": (0..1000).collect::<Vec<_>>()}))
}

#[tauri::command]
fn finish(nonce: String, checksum: u64) -> Result<bool, String> {
    let expected = std::env::var("TINYJS_BENCH_NONCE").map_err(|e| e.to_string())?;
    let marker = std::env::var("TINYJS_BENCH_READY").map_err(|e| e.to_string())?;
    if nonce != expected || checksum != 499500 {
        return Err("Invalid benchmark challenge".into());
    }
    std::fs::write(
        marker,
        serde_json::json!({"nonce": nonce, "checksum": checksum}).to_string(),
    )
    .map_err(|e| e.to_string())?;
    Ok(true)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![challenge, finish])
        .run(tauri::generate_context!())
        .expect("benchmark application failed");
}
