// Analyse a text with the SlopTotal JSON API, using only the Go standard library.
//
// Usage: go run ./examples/go_client "some text..." [--base URL]
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
)

const defaultBase = "http://localhost:8000"

type AnalysisResponse struct {
	OverallScore   float64        `json:"overall_score"`
	OverallVerdict string         `json:"overall_verdict"`
	EngineResults  []EngineResult `json:"engine_results"`
}

type EngineResult struct {
	EngineName string  `json:"engine_name"`
	Score      float64 `json:"score"`
	Verdict    string  `json:"verdict"`
}

func main() {
	baseURL := os.Getenv("SLOPTOTAL_URL")
	if baseURL == "" {
		baseURL = defaultBase
	}

	var positional []string
	rawArgs := os.Args[1:]
	for i := 0; i < len(rawArgs); i++ {
		arg := rawArgs[i]
		if arg == "--base" && i+1 < len(rawArgs) {
			baseURL = rawArgs[i+1]
			i++
		} else if strings.HasPrefix(arg, "--base=") {
			baseURL = strings.TrimPrefix(arg, "--base=")
		} else {
			positional = append(positional, arg)
		}
	}
	baseURL = strings.TrimRight(baseURL, "/")

	var text string
	if len(positional) > 0 {
		text = positional[0]
	} else {
		stat, err := os.Stdin.Stat()
		if err == nil && (stat.Mode()&os.ModeCharDevice) == 0 {
			b, err := io.ReadAll(os.Stdin)
			if err == nil {
				text = string(b)
			}
		}
	}

	if text == "" {
		fmt.Fprintln(os.Stderr, `Usage: go run ./examples/go_client "some text..." [--base URL]`)
		os.Exit(1)
	}

	reqBody, err := json.Marshal(map[string]string{"text": text})
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error marshaling request: %v\n", err)
		os.Exit(1)
	}

	resp, err := http.Post(baseURL+"/api/analyze", "application/json", bytes.NewReader(reqBody))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Request failed: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading response: %v\n", err)
		os.Exit(1)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		fmt.Fprintf(os.Stderr, "SlopTotal returned %d: %s\n", resp.StatusCode, string(respBytes))
		os.Exit(1)
	}

	var analysis AnalysisResponse
	if err := json.Unmarshal(respBytes, &analysis); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing response: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Overall score: %.1f/100 (%s)\n", analysis.OverallScore, analysis.OverallVerdict)
	fmt.Println("Top five engines:")

	sort.Slice(analysis.EngineResults, func(i, j int) bool {
		return analysis.EngineResults[i].Score > analysis.EngineResults[j].Score
	})

	limit := 5
	if len(analysis.EngineResults) < limit {
		limit = len(analysis.EngineResults)
	}
	for _, engine := range analysis.EngineResults[:limit] {
		fmt.Printf("  %s: %.1f%%\n", engine.EngineName, engine.Score*100)
	}
}
