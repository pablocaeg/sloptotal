// SlopTotal Go example client — standard library only.
//
// Analyse a text with the SlopTotal JSON API and print the overall score,
// the verdict and the five engines with the highest scores.
//
// Usage:
//
//	go run examples/go_client/main.go "some text..." [--base URL]
//
// --base defaults to http://localhost:8000.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
)

const defaultBase = "http://localhost:8000"

type engineResult struct {
	EngineName string  `json:"engine_name"`
	Score     float64 `json:"score"`
	Verdict   string  `json:"verdict"`
}

type analysis struct {
	OverallScore   float64        `json:"overall_score"`
	OverallVerdict string         `json:"overall_verdict"`
	EngineResults  []engineResult `json:"engine_results"`
}

func main() {
	base := flag.String("base", defaultBase, "base URL of the SlopTotal server")
	flag.Parse()

	args := flag.Args()
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, `Usage: go run examples/go_client/main.go "some text..." [--base URL]`)
		os.Exit(1)
	}
	text := args[0]

	// Trim trailing slashes from base
	for len(*base) > 0 && (*base)[len(*base)-1] == '/' {
		*base = (*base)[:len(*base)-1]
	}

	payload, err := json.Marshal(map[string]string{"text": text})
	if err != nil {
		fmt.Fprintf(os.Stderr, "error marshalling request: %v\n", err)
		os.Exit(1)
	}

	resp, err := http.Post(*base+"/api/analyze", "application/json", bytes.NewReader(payload))
	if err != nil {
		fmt.Fprintf(os.Stderr, "error calling SlopTotal: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Fprintf(os.Stderr, "SlopTotal returned %d: %s\n", resp.StatusCode, body)
		os.Exit(1)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error reading response: %v\n", err)
		os.Exit(1)
	}

	var a analysis
	if err := json.Unmarshal(body, &a); err != nil {
		fmt.Fprintf(os.Stderr, "error parsing JSON: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Overall score: %.1f/100 (%s)\n", a.OverallScore, a.OverallVerdict)
	fmt.Println("Top five engines:")

	sort.Slice(a.EngineResults, func(i, j int) bool {
		return a.EngineResults[i].Score > a.EngineResults[j].Score
	})

	for i, eng := range a.EngineResults {
		if i >= 5 {
			break
		}
		fmt.Printf("  %s: %.1f%%\n", eng.EngineName, eng.Score*100)
	}
}
