import os
import subprocess
import pytest
from tests.conftest import sloptotal_available


@pytest.mark.skipif(not sloptotal_available(), reason="SlopTotal not available")
@pytest.mark.skipif(not os.path.exists("cargo") or os.system("cargo --version > /dev/null 2>&1") != 0, reason="Cargo not installed")
def test_rust_client():
    """Test the Rust client example"""
    # Build the Rust client
    build_dir = "examples/rust_client"
    result = subprocess.run(["cargo", "build"], cwd=build_dir, capture_output=True, text=True)
    assert result.returncode == 0, f"Build failed: {result.stderr}"
    
    # Test with text argument
    test_text = "This is a test sentence."
    result = subprocess.run(
        ["./target/debug/sloptotal-client", "--text", test_text], 
        cwd=build_dir, 
        capture_output=True, 
        text=True
    )
    assert result.returncode == 0, f"Client failed: {result.stderr}"
    assert "Overall score:" in result.stdout
    assert "Top five engines:" in result.stdout
    
    # Test with stdin
    result = subprocess.run(
        ["./target/debug/sloptotal-client"], 
        cwd=build_dir, 
        input=test_text, 
        capture_output=True, 
        text=True
    )
    assert result.returncode == 0, f"Client failed: {result.stderr}"
    assert "Overall score:" in result.stdout
    assert "Top five engines:" in result.stdout
    
    # Test with custom base URL
    result = subprocess.run(
        ["./target/debug/sloptotal-client", "--text", test_text, "--base", "http://localhost:8000"], 
        cwd=build_dir, 
        capture_output=True, 
        text=True
    )
    assert result.returncode == 0, f"Client failed: {result.stderr}"
    assert "Overall score:" in result.stdout
    assert "Top five engines:" in result.stdout
