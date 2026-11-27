// Analyse a text with the SlopTotal JSON API.
//
// Usage: cargo run --manifest-path examples/rust_client/Cargo.toml -- "some text..." [--base URL]
// The text can also be piped on stdin. SLOPTOTAL_URL sets the base URL.
use std::io::{self, IsTerminal, Read};
use std::process;

use serde::Deserialize;

const DEFAULT_BASE: &str = "http://localhost:8000";

#[derive(Deserialize)]
struct AnalysisResponse {
    overall_score: f64,
    overall_verdict: String,
    engine_results: Vec<EngineResult>,
}

#[derive(Deserialize)]
struct EngineResult {
    engine_name: String,
    score: f64,
}

fn usage() -> ! {
    eprintln!(
        "Usage: cargo run --manifest-path examples/rust_client/Cargo.toml -- \"some text...\" [--base URL]"
    );
    process::exit(1);
}

fn main() {
    let mut base = std::env::var("SLOPTOTAL_URL").unwrap_or_default();
    if base.is_empty() {
        base = DEFAULT_BASE.to_string();
    }

    let mut positional: Vec<String> = Vec::new();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--base" {
            match args.next() {
                Some(value) => base = value,
                None => usage(),
            }
        } else if let Some(value) = arg.strip_prefix("--base=") {
            base = value.to_string();
        } else {
            positional.push(arg);
        }
    }
    let base = base.trim_end_matches('/').to_string();

    let mut text = positional.into_iter().next().unwrap_or_default();
    if text.is_empty() && !io::stdin().is_terminal() {
        let mut piped = String::new();
        if io::stdin().read_to_string(&mut piped).is_ok() {
            text = piped;
        }
    }
    if text.is_empty() {
        usage();
    }

    let client = reqwest::blocking::Client::new();
    let response = match client
        .post(format!("{base}/api/analyze"))
        .json(&serde_json::json!({ "text": text }))
        .send()
    {
        Ok(response) => response,
        Err(err) => {
            eprintln!("Request failed: {err}");
            process::exit(1);
        }
    };

    let status = response.status();
    if !status.is_success() {
        let body = response.text().unwrap_or_default();
        eprintln!("SlopTotal returned {}: {}", status.as_u16(), body);
        process::exit(1);
    }

    let mut analysis: AnalysisResponse = match response.json() {
        Ok(analysis) => analysis,
        Err(err) => {
            eprintln!("Error parsing response: {err}");
            process::exit(1);
        }
    };

    println!(
        "Overall score: {:.1}/100 ({})",
        analysis.overall_score, analysis.overall_verdict
    );
    println!("Top five engines:");

    analysis
        .engine_results
        .sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    for engine in analysis.engine_results.iter().take(5) {
        println!("  {}: {:.1}%", engine.engine_name, engine.score * 100.0);
    }
}
