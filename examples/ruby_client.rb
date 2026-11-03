# Analyse a text with the SlopTotal JSON API, using only the Ruby standard library.
#
# Usage: ruby examples/ruby_client.rb "some text..." [--base URL]

require "json"
require "net/http"
require "uri"

DEFAULT_BASE = "http://localhost:8000"

args = ARGV.dup
base = DEFAULT_BASE
base_flag = args.index("--base")
if base_flag
  base = args[base_flag + 1].to_s
  args.slice!(base_flag, 2)
end
base = base.sub(%r{/+\z}, "")

text = args.first
if text.nil? || text.empty? || base.empty?
  warn 'Usage: ruby examples/ruby_client.rb "some text..." [--base URL]'
  exit 1
end

uri = URI("#{base}/api/analyze")
response = Net::HTTP.post(uri, JSON.generate({ text: text }), "Content-Type" => "application/json")
unless response.is_a?(Net::HTTPSuccess)
  warn "SlopTotal returned #{response.code}: #{response.body}"
  exit 1
end
analysis = JSON.parse(response.body)

puts format("Overall score: %.1f/100 (%s)", analysis["overall_score"], analysis["overall_verdict"])
puts "Top five engines:"
top_engines = analysis["engine_results"].sort_by { |engine| -engine["score"] }.first(5)
top_engines.each do |engine|
  puts format("  %s: %.1f%%", engine["engine_name"], engine["score"] * 100)
end
