#!/usr/bin/env python3
"""Compile protobuf schemas to Python modules."""
import os
import subprocess
import sys
from pathlib import Path


def compile_proto_files():
    """Compile all proto files to Python modules."""
    # Get project root
    project_root = Path(__file__).parent.parent
    proto_dir = project_root / "proto"
    
    # Create output directory
    output_dir = project_root / "bitquery_proto"
    output_dir.mkdir(exist_ok=True)
    
    # Create __init__.py files
    (output_dir / "__init__.py").touch()
    (output_dir / "solana" / "__init__.py").parent.mkdir(exist_ok=True)
    (output_dir / "solana" / "__init__.py").touch()
    
    # Find all proto files
    proto_files = list(proto_dir.rglob("*.proto"))
    
    if not proto_files:
        print("No proto files found in", proto_dir)
        return False
    
    print(f"Found {len(proto_files)} proto files to compile")
    
    # Compile proto files
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
    ] + [str(f) for f in proto_files]
    
    print("Running:", " ".join(cmd))
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Successfully compiled proto files")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error compiling proto files: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


if __name__ == "__main__":
    success = compile_proto_files()
    sys.exit(0 if success else 1)