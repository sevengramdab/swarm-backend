"""
ToolExecutor — Direct local execution of file, shell, and web tools in the workspace.
This allows subagents in swarm mode to actually DO work instead of just generating text essays.
"""

import os
import subprocess
import glob
import urllib.request
import urllib.parse
import re
import ast
import operator
import math
from typing import Dict, Any

from core import config


def _get_workspace_root() -> str:
    """Attempt to find the workspace root from common markers."""
    # Prefer the workspace root set by the extension
    if config.WORKSPACE_ROOT and os.path.isdir(config.WORKSPACE_ROOT):
        return config.WORKSPACE_ROOT
    cwd = os.getcwd()
    markers = ['.git', 'package.json', 'pyproject.toml', 'requirements.txt', 'README.md']
    current = cwd
    for _ in range(5):
        for marker in markers:
            if os.path.exists(os.path.join(current, marker)):
                return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return cwd


# Note: call _get_workspace_root() dynamically — config.WORKSPACE_ROOT may be updated at runtime
# WORKSPACE_ROOT = _get_workspace_root()  # removed: evaluated lazily below


def _resolve_path(file_path: str) -> str:
    """Resolve a relative path against the workspace root."""
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(_get_workspace_root(), file_path)


def _safe_eval(expr: str) -> Any:
    """Safely evaluate a math expression using AST.
    Supports: +, -, *, /, //, %, **, sqrt(), abs(), round(), min(), max()
    """
    _ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
    }

    _funcs = {
        'sqrt': math.sqrt,
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'pow': pow,
    }

    def _eval(node):
        if isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.Constant):  # Python >= 3.8
            return node.value
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ops:
                raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
            return _ops[op_type](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ops:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            return _ops[op_type](_eval(node.operand))
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls are supported")
            func_name = node.func.id
            if func_name not in _funcs:
                raise ValueError(f"Unsupported function: {func_name}. Allowed: {', '.join(_funcs.keys())}")
            args = [_eval(arg) for arg in node.args]
            return _funcs[func_name](*args)
        elif isinstance(node, ast.Expression):
            return _eval(node.body)
        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    try:
        tree = ast.parse(expr, mode='eval')
        return _eval(tree)
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")


def _web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web using DuckDuckGo HTML API (no key required)."""
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Try multiple regex patterns for DuckDuckGo result blocks
        results = []
        patterns = [
            # Classic DuckDuckGo
            r'<a[^>]*class="result__a"[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>',
            # Alternative format
            r'<a[^>]*href="(https?://[^"]+)"[^>]*class="result__a"[^>]*>([^<]+)</a>',
            # Result title links
            r'<a[^>]*href="(https?://[^"]+)"[^>]*class="result__snippet"[^>]*>([^<]+)</a>',
            # Generic result links
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>([^<]{10,200})</a>',
        ]
        for pattern in patterns:
            if len(results) >= max_results:
                break
            for match in re.finditer(pattern, html, re.IGNORECASE):
                href = match.group(1)
                title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                if href and title and len(title) > 5 and 'duckduckgo' not in href.lower():
                    if not any(r["url"] == href for r in results):
                        results.append({"title": title, "url": href})
                if len(results) >= max_results:
                    break

        if not results:
            # Fallback: try to extract any useful text snippets from the HTML
            snippets = []
            for match in re.finditer(r'<[^>]*class="result__snippet"[^>]*>([^<]{30,500})</a>', html):
                text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if text:
                    snippets.append(text)
            if snippets:
                return {"status": "ok", "data": {"results": [{"title": "Search snippet", "url": "", "snippet": s} for s in snippets[:max_results]], "query": query, "note": "Results found as text snippets."}, "error": ""}
            return {"status": "ok", "data": {"results": [], "query": query, "note": "No results found. Use known market data from templates/etsy_listing_guide.md instead."}, "error": ""}

        return {"status": "ok", "data": {"results": results[:max_results], "query": query}, "error": ""}
    except Exception as e:
        return {"status": "error", "data": None, "error": f"Web search failed: {str(e)}. Use known market data from templates/etsy_listing_guide.md instead."}


def execute_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool directly in the local workspace.
    Returns a dict matching the extension's tool result format.
    """
    try:
        if tool == "read_file":
            path_arg = args.get("path", "") or args.get("file", "") or args.get("filename", "")
            if not path_arg:
                return {"status": "error", "data": None, "error": "Missing required argument: path. Use args={\"path\": \"<file path>\"}"}
            path = _resolve_path(path_arg)
            if not os.path.exists(path):
                return {"status": "error", "data": None, "error": f"File not found: {path}"}
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return {"status": "ok", "data": {"content": content}, "error": ""}

        elif tool == "write_file":
            path_arg = args.get("path", "")
            if not path_arg:
                return {"status": "error", "data": None, "error": "Missing required argument: path. Use args={\"path\": \"<file path>\", \"content\": \"<content>\"}"}
            path = _resolve_path(path_arg)
            content = args.get("content", "")
            if content is None:
                return {"status": "error", "data": None, "error": "Missing required argument: content. Use args={\"path\": \"<file path>\", \"content\": \"<content>\"}"}
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            original = None
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    original = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"status": "ok", "data": {"path": path_arg, "size": len(content)}, "error": ""}

        elif tool == "list_files":
            dir_path = _resolve_path(args.get("path", "."))
            if not os.path.exists(dir_path):
                return {"status": "error", "data": None, "error": f"Directory not found: {dir_path}"}
            entries = []
            try:
                for name in os.listdir(dir_path):
                    full = os.path.join(dir_path, name)
                    entries.append({"name": name, "type": "directory" if os.path.isdir(full) else "file"})
            except PermissionError:
                return {"status": "error", "data": None, "error": f"Permission denied: {dir_path}"}
            return {"status": "ok", "data": {"files": entries}, "error": ""}

        elif tool == "run_command":
            command = args.get("command", "")
            if not command:
                return {"status": "error", "data": None, "error": "No command provided"}
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=_get_workspace_root(),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return {
                    "status": "ok" if result.returncode == 0 else "error",
                    "data": {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "code": result.returncode,
                    },
                    "error": result.stderr if result.returncode != 0 else "",
                }
            except subprocess.TimeoutExpired:
                return {"status": "error", "data": {"stdout": "", "stderr": "", "code": -1}, "error": "Command timed out after 30s"}
            except Exception as e:
                return {"status": "error", "data": {"stdout": "", "stderr": "", "code": -1}, "error": str(e)}

        elif tool == "search_files":
            query = args.get("query", "")
            if not query:
                return {"status": "error", "data": None, "error": "No query provided"}
            pattern = f"**/*{query}*" if "*" not in query else query
            try:
                matches = glob.glob(pattern, root_dir=_get_workspace_root(), recursive=True)
                # Filter out common noise
                filtered = [m for m in matches if "node_modules" not in m and "__pycache__" not in m and ".git" not in m]
                return {"status": "ok", "data": {"files": filtered[:50]}, "error": ""}
            except Exception as e:
                return {"status": "error", "data": None, "error": str(e)}

        elif tool == "web_search":
            query = args.get("query", "")
            if not query:
                return {"status": "error", "data": None, "error": "No search query provided"}
            max_results = args.get("max_results", 5)
            return _web_search(query, max_results)

        elif tool == "calculate":
            expression = args.get("expression", "")
            if not expression:
                return {"status": "error", "data": None, "error": "Missing required argument: expression. Use args={\"expression\": \"<math expression>\"}"}
            try:
                result = _safe_eval(expression)
                return {"status": "ok", "data": {"expression": expression, "result": result}, "error": ""}
            except Exception as e:
                return {"status": "error", "data": None, "error": f"Calculation error: {str(e)}"}

        elif tool == "etsy_profit_calculator":
            """Calculate Etsy profit margins including all platform fees.
            Args: selling_price, product_cost, shipping_cost, quantity=1, offsite_ads_rate=0
            """
            try:
                selling_price = float(args.get("selling_price", 0))
                product_cost = float(args.get("product_cost", 0))
                shipping_cost = float(args.get("shipping_cost", 0))
                quantity = int(args.get("quantity", 1))
                offsite_ads_rate = float(args.get("offsite_ads_rate", 0))  # 0, 12, or 15

                if selling_price <= 0:
                    return {"status": "error", "data": None, "error": "selling_price must be > 0"}

                total_revenue = (selling_price + shipping_cost) * quantity

                # Etsy fees
                listing_fee = 0.20 * quantity
                transaction_fee_rate = 0.065
                transaction_fee = (selling_price + shipping_cost) * transaction_fee_rate * quantity
                payment_processing_rate = 0.03
                payment_processing_fee = ((selling_price + shipping_cost) * payment_processing_rate + 0.25) * quantity
                offsite_ads_fee = (selling_price * (offsite_ads_rate / 100)) * quantity if offsite_ads_rate > 0 else 0

                total_etsy_fees = listing_fee + transaction_fee + payment_processing_fee + offsite_ads_fee
                total_product_cost = product_cost * quantity
                total_shipping_cost = shipping_cost * quantity
                total_costs = total_product_cost + total_etsy_fees
                net_profit = (selling_price * quantity) - total_costs
                profit_margin = (net_profit / (selling_price * quantity)) * 100 if selling_price > 0 else 0
                break_even_units = total_etsy_fees / (selling_price - product_cost) if (selling_price - product_cost) > 0 else float('inf')

                return {
                    "status": "ok",
                    "data": {
                        "quantity": quantity,
                        "revenue": round(selling_price * quantity, 2),
                        "shipping_charged": round(shipping_cost * quantity, 2),
                        "total_revenue": round(total_revenue, 2),
                        "fees": {
                            "listing_fee": round(listing_fee, 2),
                            "transaction_fee_6_5_pct": round(transaction_fee, 2),
                            "payment_processing_3pct_plus_25c": round(payment_processing_fee, 2),
                            "offsite_ads_fee": round(offsite_ads_fee, 2),
                            "total_etsy_fees": round(total_etsy_fees, 2),
                        },
                        "costs": {
                            "product_cost": round(total_product_cost, 2),
                            "etsy_fees": round(total_etsy_fees, 2),
                            "total_costs": round(total_costs, 2),
                        },
                        "profit": {
                            "net_profit": round(net_profit, 2),
                            "profit_margin_pct": round(profit_margin, 2),
                            "break_even_units": round(break_even_units, 2) if break_even_units != float('inf') else "N/A",
                        },
                        "recommended_min_price": round((product_cost + total_etsy_fees / quantity) / 0.65, 2),
                    },
                    "error": "",
                }
            except Exception as e:
                return {"status": "error", "data": None, "error": f"Profit calculation error: {str(e)}. Use args=" + '{"selling_price": 25.00, "product_cost": 8.50, "shipping_cost": 4.99, "quantity": 1}'}

        elif tool == "etsy_research":
            """Research Etsy trends, competitors, or product ideas using web search."""
            query = args.get("query", "")
            if not query:
                return {"status": "error", "data": None, "error": "Missing required argument: query. Use args={\"query\": \"trending Etsy products 2024\"}"}
            search_query = f"site:etsy.com OR Etsy {query}"
            max_results = args.get("max_results", 5)
            return _web_search(search_query, max_results)

        elif tool == "etsy_pricing_optimizer":
            """Calculate optimal Etsy pricing based on cost, target margin, and competitor data.
            Args: product_cost, shipping_cost=0, target_margin=40, competitor_low=0, competitor_high=0
            """
            try:
                product_cost = float(args.get("product_cost", 0))
                shipping_cost = float(args.get("shipping_cost", 0))
                target_margin = float(args.get("target_margin", 40))
                competitor_low = float(args.get("competitor_low", 0))
                competitor_high = float(args.get("competitor_high", 0))

                if product_cost <= 0:
                    return {"status": "error", "data": None, "error": "product_cost must be > 0"}

                # Etsy fee structure
                listing_fee = 0.20
                transaction_fee_rate = 0.065
                payment_processing_rate = 0.03
                payment_processing_fixed = 0.25

                # Calculate minimum price to hit target margin
                # margin = (revenue - costs) / revenue
                # revenue = price * quantity
                # costs = product_cost + listing_fee + (price+shipping)*0.065 + (price+shipping)*0.03 + 0.25
                # Let P = price, S = shipping, C = product_cost
                # Revenue = P
                # Costs = C + 0.20 + (P+S)*0.065 + (P+S)*0.03 + 0.25
                # Margin = (P - Costs) / P
                # target_margin/100 = (P - C - 0.20 - (P+S)*0.095 - 0.25) / P
                # Solve for P:
                # target_margin * P = 100 * (P - C - 0.45 - (P+S)*0.095)
                # target_margin * P = 100P - 100C - 45 - 9.5P - 9.5S
                # target_margin * P = P*(100 - 9.5) - 100C - 45 - 9.5S
                # P*(target_margin - 90.5) = -100C - 45 - 9.5S
                # P = (100C + 45 + 9.5S) / (90.5 - target_margin)

                denominator = 90.5 - target_margin
                if denominator <= 0:
                    min_price_for_margin = product_cost * 10  # very high margin requested
                else:
                    min_price_for_margin = (100 * product_cost + 45 + 9.5 * shipping_cost) / denominator

                # Calculate fees at min price
                revenue = min_price_for_margin
                total_revenue = revenue + shipping_cost
                fees = {
                    "listing_fee": round(listing_fee, 2),
                    "transaction_fee": round(total_revenue * transaction_fee_rate, 2),
                    "payment_processing": round(total_revenue * payment_processing_rate + payment_processing_fixed, 2),
                }
                fees["total_etsy_fees"] = round(sum(fees.values()), 2)
                total_costs = product_cost + fees["total_etsy_fees"]
                net_profit = revenue - total_costs
                actual_margin = (net_profit / revenue) * 100 if revenue > 0 else 0

                result = {
                    "optimal_price": round(min_price_for_margin, 2),
                    "target_margin_pct": target_margin,
                    "actual_margin_pct": round(actual_margin, 2),
                    "product_cost": round(product_cost, 2),
                    "shipping_cost": round(shipping_cost, 2),
                    "fees": fees,
                    "total_costs": round(total_costs, 2),
                    "net_profit_per_unit": round(net_profit, 2),
                }

                if competitor_low > 0 and competitor_high > 0:
                    avg_competitor = (competitor_low + competitor_high) / 2
                    result["competitor_range"] = f"${competitor_low:.2f} - ${competitor_high:.2f}"
                    result["competitor_avg"] = round(avg_competitor, 2)
                    if min_price_for_margin > competitor_high:
                        result["pricing_recommendation"] = f"Your target margin requires ${min_price_for_margin:.2f}, above competitor range. Consider reducing margin or differentiating."
                    elif min_price_for_margin < competitor_low:
                        result["pricing_recommendation"] = f"You can price at ${min_price_for_margin:.2f} and still beat competitors. Consider pricing at ${avg_competitor:.2f} for higher margin."
                    else:
                        result["pricing_recommendation"] = f"Price at ${min_price_for_margin:.2f} fits within competitor range. Good positioning."
                    # Suggest a sweet spot price
                    sweet_spot = max(min_price_for_margin, avg_competitor * 0.95)
                    result["suggested_price"] = round(sweet_spot, 2)
                    sweet_revenue = sweet_spot + shipping_cost
                    sweet_fees = 0.20 + sweet_revenue * 0.065 + sweet_revenue * 0.03 + 0.25
                    sweet_profit = sweet_spot - product_cost - sweet_fees
                    result["suggested_margin_pct"] = round((sweet_profit / sweet_spot) * 100, 2)
                else:
                    result["pricing_recommendation"] = f"Price at ${min_price_for_margin:.2f} to achieve {target_margin}% margin."
                    result["suggested_price"] = round(min_price_for_margin, 2)
                    result["suggested_margin_pct"] = round(actual_margin, 2)

                return {"status": "ok", "data": result, "error": ""}
            except Exception as e:
                return {"status": "error", "data": None, "error": f"Pricing optimization error: {str(e)}"}

        elif tool == "etsy_listing_template":
            """Return a structured Etsy listing template for a product."""
            product_name = args.get("product_name", "")
            category = args.get("category", "")
            if not product_name:
                return {"status": "error", "data": None, "error": "Missing required argument: product_name"}
            template = {
                "title": f"{product_name} | Handmade {category} | Personalized Gift | Unique Home Decor",
                "description_structure": [
                    "1. Hook (1-2 sentences capturing emotion/need)",
                    "2. Product details (materials, dimensions, colors)",
                    "3. Personalization options",
                    "4. Shipping & turnaround time",
                    "5. Care instructions",
                    "6. Return policy / satisfaction guarantee",
                ],
                "tags": [product_name.lower(), category.lower(), "handmade", "personalized gift", "custom", "unique", "home decor", "gift for her", "gift for him", "anniversary gift", "birthday gift", "wedding gift", "rustic decor"],
                "attributes": {
                    "occasion": ["Birthday", "Anniversary", "Wedding", "Housewarming"],
                    "recipient": ["Her", "Him", "Couple", "Family"],
                },
                "photo_tips": [
                    "Main: Product on clean background with lifestyle context",
                    "Secondary: Close-up showing material texture",
                    "Third: Product in use / lifestyle setting",
                    "Fourth: Size comparison or scale reference",
                    "Fifth: Packaging / gift-ready presentation",
                ],
            }
            return {"status": "ok", "data": template, "error": ""}

        elif tool == "get_current_weather":
            return {"status": "error", "data": None, "error": "Weather tool not available in backend."}

        elif tool == "get_time_at_location":
            return {"status": "error", "data": None, "error": "Time tool not available in backend."}

        else:
            return {"status": "error", "data": None, "error": f"Unknown tool: {tool}"}

    except Exception as e:
        return {"status": "error", "data": None, "error": f"Tool execution crashed: {str(e)}"}
