"""
Setup script for Taiwan Weather MCP Server.
This script will create a virtual environment, install dependencies, and provide instructions to run the server.
"""

import os
import subprocess
import sys
from pathlib import Path

def main():
    """Main setup function to prepare the environment and provide running instructions."""
    print("Setting up Taiwan Weather MCP Server...")
    
    # Get the current directory
    current_dir = Path(__file__).parent.absolute()
    
    # Check if .env file exists, create if not
    env_file = current_dir / ".env"
    if not env_file.exists():
        print("\nCreating .env file. Please update with your CWA API key.")
        with open(env_file, "w") as f:
            f.write("# Central Weather Administration API key\n")
            f.write("CWA_API_KEY=your_api_key_here\n\n")
    
    # Install dependencies using uv
    print("\nInstalling dependencies using uv...")
    try:
        subprocess.run(["uv", "pip", "install", "-r", str(current_dir / "requirements.txt")], check=True)
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        sys.exit(1)
    
    # Print instructions
    print("\n" + "=" * 70)
    print("Setup complete! Follow these steps to run the server and configure Claude Desktop:")
    print("=" * 70)
    print("1. Make sure you've updated the .env file with your CWA API key")
    print("   You can obtain one from: https://opendata.cwa.gov.tw/user/authkey")
    print("=" * 70)

if __name__ == "__main__":
    main()