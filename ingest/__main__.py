"""
Entry point for running the ingest module
"""
import asyncio
from . import main

if __name__ == '__main__':
    asyncio.run(main()) 