use clap::Parser;
use serde::{Deserialize, Serialize};
use std::env;
use std::io::{self, Read};
use std::process;

const DEFAULT_BASE: &str = "http://localhost:8000";

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[arg(short, long, help = "Text to analyze")]
    text: Option<String>,
    
    #[arg(long, help = "Base URL of SlopTotal server")]
    base: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct AnalysisResponse {
    overall_score: f64,
    overall_verdict: String,
    engine_results: Vec<EngineResult>,
}

#[derive(Debug, Serialize, Deserialize)]
struct EngineResult {
    engine_name: String,
    score: f64,
    verdict: String,
}

fn main() {
    let args = Args::parse();
    
    let base_url = args.base
        .or_else(|| env::var("SLOPTOTAL_URL").ok())
        .unwrap_or_else(|| DEFAULT_BASE.to_string());
    
    let base_url = base_url.trim_end_matches('/');
    
    let text = match args.text {
        Some(t) => t,
        None => {
            let mut input = String::new();
            if io::stdin().read_to_string(&mut input).is_ok() {
                input.trim().to_string()
            } else {
                eprintln!("Usage: {} 'text...' [--base URL]", env::args().next().unwrap_or_else(|| "./target/debug/sloptotal-client".to_string()));
                process::exit(1);
            }
        }
    };
    
    if text.is_empty() {
        eprintln!("Error: No text provided");
        process::exit(1);
    }
    
    let client = match reqwest::blocking::Client::new() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error creating HTTP client: {}", e);
            process::exit(1);
        }
    };
    
    let response = match client
        .post(format!("{}/api/analyze", base_url))
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({"text": text}))
        .send()
    {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Request failed: {}", e);
            process::exit(1);
        }
    };
    
    if !response.status().is_success() {
        eprintln!("SlopTotal returned {}: {}", response.status(), response.text().unwrap_or_else(|_| ""));
        process::exit(1);
    }
    
    let analysis: AnalysisResponse = match response.json() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("Error parsing response: {}", e);
            process::exit(1);
        }
    };
    
    println!("Overall score: {:.1}/100 ({})", analysis.overall_score, analysis.overall_verdict);
    println!("Top five engines:");
    
    let mut sorted_engines = analysis.engine_results;
    sorted_engines.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    
    let limit = std::cmp::min(5, sorted_engines.len());
    for engine in &sorted_engines[..limit] {
        println!("  {}: {:.1}%", engine.engine_name, engine.score * 100.0);
    }
}