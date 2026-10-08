#!/usr/bin/env python3
"""Run from the repository root; actual writes require the isolated wrapper."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/backend'))
from app.services.evaluation.benchmark.runner import main
if __name__=='__main__':raise SystemExit(main())
