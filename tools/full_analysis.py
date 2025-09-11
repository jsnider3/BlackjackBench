#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import tempfile
import shutil


def run_tool(tool_path: str, args: List[str], capture_output: bool = True) -> Dict[str, Any]:
    """Run a tool and capture its output."""
    cmd = [sys.executable, tool_path] + args
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        else:
            result = subprocess.run(cmd, check=True)
            return {
                "success": True,
                "stdout": "",
                "stderr": "",
                "returncode": result.returncode
            }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "stdout": e.stdout if hasattr(e, 'stdout') else "",
            "stderr": e.stderr if hasattr(e, 'stderr') else "",
            "returncode": e.returncode,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": str(e)
        }


def generate_html_report(analyses: Dict[str, Any], output_path: str, title: str = "BlackJack Bench Analysis") -> None:
    """Generate a comprehensive HTML report."""
    
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 15px; }}
        h3 {{ color: #7f8c8d; }}
        .summary {{ background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric-value {{ font-size: 1.5em; font-weight: bold; color: #2980b9; }}
        .metric-label {{ font-size: 0.9em; color: #7f8c8d; }}
        pre {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #bdc3c7; }}
        th {{ background-color: #34495e; color: white; }}
        tr:hover {{ background-color: #ecf0f1; }}
        .error {{ background: #e74c3c; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        .success {{ background: #27ae60; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        .warning {{ background: #f39c12; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        .collapsible {{ cursor: pointer; padding: 10px; background: #34495e; color: white; border: none; width: 100%; text-align: left; border-radius: 5px; margin: 5px 0; }}
        .collapsible:hover {{ background: #2c3e50; }}
        .content {{ max-height: 0; overflow: hidden; transition: max-height 0.2s ease-out; background: #ecf0f1; border-radius: 0 0 5px 5px; }}
        .content.active {{ max-height: 1000px; padding: 15px; }}
        .timestamp {{ color: #95a5a6; font-size: 0.9em; }}
    </style>
    <script>
        function toggleContent(element) {{
            const content = element.nextElementSibling;
            content.classList.toggle('active');
            element.textContent = content.classList.contains('active') ? 
                element.textContent.replace('▶', '▼') : 
                element.textContent.replace('▼', '▶');
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="timestamp">Generated on {timestamp}</div>
        
        {content}
    </div>
</body>
</html>"""

    # Build content sections
    content_sections = []
    
    # Executive Summary
    if "summary" in analyses:
        summary = analyses["summary"]
        content_sections.append(f"""
        <h2>Executive Summary</h2>
        <div class="summary">
            <div class="metric">
                <div class="metric-value">{summary.get('total_models', 0)}</div>
                <div class="metric-label">Models Analyzed</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('best_model', 'N/A')}</div>
                <div class="metric-label">Best Performing Model</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('best_ev', 0):.3f}</div>
                <div class="metric-label">Best Weighted EV</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('total_decisions', 0):,}</div>
                <div class="metric-label">Total Decisions Analyzed</div>
            </div>
        </div>
        """)
    
    # Model Comparison
    if "comparison" in analyses and analyses["comparison"]["success"]:
        content_sections.append(f"""
        <h2>Model Comparison</h2>
        <button class="collapsible" onclick="toggleContent(this)">▶ Model Performance Comparison</button>
        <div class="content">
            <pre>{analyses["comparison"]["stdout"]}</pre>
        </div>
        """)
    
    # Top Leaks Analysis
    if "top_leaks" in analyses:
        for model, result in analyses["top_leaks"].items():
            if result["success"]:
                content_sections.append(f"""
                <button class="collapsible" onclick="toggleContent(this)">▶ Top Strategic Leaks - {model}</button>
                <div class="content">
                    <pre>{result["stdout"]}</pre>
                </div>
                """)
    
    # Confusion Matrices
    if "confusion" in analyses:
        for model, result in analyses["confusion"].items():
            if result["success"]:
                content_sections.append(f"""
                <button class="collapsible" onclick="toggleContent(this)">▶ Confusion Matrix - {model}</button>
                <div class="content">
                    <pre>{result["stdout"]}</pre>
                </div>
                """)
    
    # Thinking Analysis
    if "thinking" in analyses:
        for model, result in analyses["thinking"].items():
            if result["success"]:
                # Only include if there's actual thinking data (not just "No thinking tokens found")
                stdout = result["stdout"]
                if "No thinking tokens found" not in stdout and "thinking tokens:" in stdout:
                    content_sections.append(f"""
                    <button class="collapsible" onclick="toggleContent(this)">▶ Thinking Load Analysis - {model}</button>
                    <div class="content">
                        <pre>{stdout}</pre>
                    </div>
                    """)
    
    # Strategy Consistency
    if "strategy_consistency" in analyses and analyses["strategy_consistency"]["success"]:
        content_sections.append(f"""
        <h2>Strategy Consistency Analysis</h2>
        <button class="collapsible" onclick="toggleContent(this)">▶ Stated vs Actual Strategy Compliance</button>
        <div class="content">
            <pre>{analyses["strategy_consistency"]["stdout"]}</pre>
        </div>
        """)
    
    # Errors and Warnings
    errors = []
    for analysis_type, results in analyses.items():
        if isinstance(results, dict):
            if not results.get("success", True):
                errors.append(f"{analysis_type}: {results.get('error', 'Unknown error')}")
            elif isinstance(results, dict) and "success" not in results:
                # Check nested results
                for subkey, subresult in results.items():
                    if isinstance(subresult, dict) and not subresult.get("success", True):
                        errors.append(f"{analysis_type}.{subkey}: {subresult.get('error', 'Unknown error')}")
    
    if errors:
        error_content = "<br>".join(errors)
        content_sections.append(f"""
        <h2>Errors and Warnings</h2>
        <div class="error">
            {error_content}
        </div>
        """)
    
    # Join all content
    content = "\n".join(content_sections)
    
    # Generate final HTML
    html = html_template.format(
        title=title,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        content=content
    )
    
    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser(description="Comprehensive BlackJack analysis pipeline")
    ap.add_argument("inputs", nargs="+", help="JSONL files, directories, or globs to analyze")
    ap.add_argument("--output", "-o", default="analysis_report.html", help="Output HTML report path")
    ap.add_argument("--title", default="BlackJack Bench Analysis", help="Report title")
    ap.add_argument("--models", help="Comma-separated list of models to focus on")
    ap.add_argument("--include-strategy", action="store_true", help="Include strategy consistency analysis")
    ap.add_argument("--strategy-dir", default="model_thoughts", help="Directory with model strategy files")
    ap.add_argument("--compare-only", action="store_true", help="Only run model comparison (faster)")
    ap.add_argument("--thinking-analysis", action="store_true", help="Include thinking load analysis for applicable models")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid")
    ap.add_argument("--working-dir", help="Working directory for temporary files")
    args = ap.parse_args()
    
    # Setup working directory
    if args.working_dir:
        work_dir = Path(args.working_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="blackjack_analysis_"))
    
    print(f"BlackJack Bench Full Analysis Pipeline")
    print(f"Working directory: {work_dir}")
    print(f"Output report: {args.output}")
    
    # Get the tools directory
    script_dir = Path(__file__).parent
    
    analyses = {}
    
    try:
        # 1. Model Comparison (always run)
        print("\n1. Running model comparison...")
        comparison_args = args.inputs + ["--track", args.track, "--statistical"]
        if args.models:
            comparison_args.extend(["--models", args.models])
        
        analyses["comparison"] = run_tool(
            str(script_dir / "compare_models.py"),
            comparison_args
        )
        
        if analyses["comparison"]["success"]:
            print("✓ Model comparison completed")
        else:
            print(f"✗ Model comparison failed: {analyses['comparison'].get('error', 'Unknown error')}")
        
        if args.compare_only:
            print("Compare-only mode: skipping detailed analysis")
        else:
            # 2. Individual model analysis
            print("\n2. Running individual model analysis...")
            
            # Discover input files for individual analysis
            from common import discover_files
            files = discover_files(args.inputs)
            
            # Filter by models if specified
            if args.models:
                model_filters = [m.strip().lower() for m in args.models.split(",")]
                files = [f for f in files if any(filter_name in f.name.lower() for filter_name in model_filters)]
            
            # Top leaks analysis
            analyses["top_leaks"] = {}
            print("  Running top leaks analysis...")
            for file in files:
                from common import extract_model_name
                model_name = extract_model_name(file)
                analyses["top_leaks"][model_name] = run_tool(
                    str(script_dir / "top_leaks.py"),
                    [str(file), "--top", "10"]
                )
            
            # Confusion matrices
            analyses["confusion"] = {}
            print("  Running confusion matrix analysis...")
            for file in files:
                from common import extract_model_name
                model_name = extract_model_name(file)
                analyses["confusion"][model_name] = run_tool(
                    str(script_dir / "summarize_confusion.py"),
                    [str(file), "--track", args.track]
                )
            
            # Thinking analysis (if requested and applicable)
            if args.thinking_analysis:
                analyses["thinking"] = {}
                print("  Running thinking load analysis...")
                for file in files:
                    # Only analyze files that likely have thinking data
                    if "thinking" in file.name.lower() or "gemini" in file.name.lower():
                        model_name = file.stem.split("_")[-1] if "_" in file.stem else file.stem
                        analyses["thinking"][model_name] = run_tool(
                            str(script_dir / "thinking_load.py"),
                            [str(file), "--first-only", "--top", "5", "--bottom", "5"]
                        )
        
        # 3. Strategy consistency (if requested)
        if args.include_strategy:
            print("\n3. Running strategy consistency analysis...")
            strategy_dir = Path(args.strategy_dir)
            if strategy_dir.exists():
                strategy_args = [str(strategy_dir), args.inputs[0] if len(args.inputs) == 1 else "baselines"]
                if args.models:
                    # For strategy consistency, we need to check each model individually
                    for model in args.models.split(","):
                        model = model.strip()
                        strategy_result = run_tool(
                            str(script_dir / "strategy_consistency.py"),
                            strategy_args + ["--model", model]
                        )
                        if not analyses.get("strategy_consistency"):
                            analyses["strategy_consistency"] = strategy_result
                        else:
                            # Combine outputs
                            if strategy_result["success"]:
                                analyses["strategy_consistency"]["stdout"] += "\n" + strategy_result["stdout"]
                else:
                    analyses["strategy_consistency"] = run_tool(
                        str(script_dir / "strategy_consistency.py"),
                        strategy_args
                    )
                
                if analyses["strategy_consistency"]["success"]:
                    print("✓ Strategy consistency analysis completed")
                else:
                    print(f"✗ Strategy consistency analysis failed: {analyses['strategy_consistency'].get('error', 'Unknown error')}")
            else:
                print(f"✗ Strategy directory not found: {strategy_dir}")
                analyses["strategy_consistency"] = {
                    "success": False,
                    "error": f"Strategy directory not found: {strategy_dir}"
                }
        
        # 4. Generate summary statistics
        print("\n4. Generating summary...")
        summary = {
            "total_models": 0,
            "best_model": "N/A",
            "best_ev": float('-inf'),
            "total_decisions": 0
        }
        
        # Parse comparison output for summary stats
        if analyses["comparison"]["success"]:
            lines = analyses["comparison"]["stdout"].split('\n')
            model_count = 0
            for line in lines:
                # Look for data lines with specific column count (avoid headers and separators)
                stripped = line.strip()
                if not stripped or stripped.startswith('Model') or stripped.startswith('#'):
                    continue
                # Skip separator lines (all dashes)
                if set(stripped.replace(' ', '')) <= {'-'}:
                    continue
                
                parts = stripped.split()
                if len(parts) >= 6:  # Ensure we have at least basic columns
                    try:
                        model_name = parts[0]
                        decisions = int(parts[1])
                        mistakes = int(parts[2])
                        # EV is always in position 4 regardless of thinking columns
                        ev = float(parts[4])
                        
                        model_count += 1
                        summary["total_decisions"] += decisions
                        if ev > summary["best_ev"]:
                            summary["best_ev"] = ev
                            summary["best_model"] = model_name
                    except (ValueError, IndexError):
                        continue
            summary["total_models"] = model_count
        
        analyses["summary"] = summary
        
        # 5. Generate HTML report
        print(f"\n5. Generating HTML report: {args.output}")
        generate_html_report(analyses, args.output, args.title)
        print("✓ HTML report generated successfully")
        
        # Summary
        print(f"\n📊 Analysis Complete!")
        print(f"   Models analyzed: {summary['total_models']}")
        print(f"   Total decisions: {summary['total_decisions']:,}")
        print(f"   Best model: {summary['best_model']} (EV: {summary['best_ev']:.6f})")
        print(f"   Report saved to: {args.output}")
        
    except Exception as e:
        print(f"\n✗ Analysis pipeline failed: {e}")
        sys.exit(1)
    
    finally:
        # Cleanup working directory if it was temporary
        if not args.working_dir and work_dir.exists():
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass


if __name__ == "__main__":
    main()