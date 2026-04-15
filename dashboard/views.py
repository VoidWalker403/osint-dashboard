from django.shortcuts import render
import subprocess
import os
import re

MOSINT_PATH = r"C:\Users\91946\go\bin\mosint.exe"
HOLEHE_PATH = "holehe"
MAIGRET_PATH = "maigret"
CONFIG_PATH = r"C:\Users\91946\.mosint.yaml"


def home(request):
    context = {
        "target": "",
        "selected_tool": "mosint",
        "top_sites": "100",
        "holehe_timeout": "8",
        "no_recursion": False,
        "parsed_lines": [],
        "legend": [
            {"sign": "+", "meaning": "Positive result / likely found / used"},
            {"sign": "-", "meaning": "Negative result / not found / not used"},
            {"sign": "x", "meaning": "Blocked, rate-limited, or failed to check"},
            {"sign": "?", "meaning": "Unclear / partial / uncertain"},
            {"sign": "[+]", "meaning": "Detailed positive line from some tools"},
            {"sign": "[-]", "meaning": "Detailed negative line from some tools"},
            {"sign": "[x]", "meaning": "Blocked or error line from some tools"},
        ],
        "raw_output": "",
    }

    if request.method == "POST":
        target = request.POST.get("target", "").strip()
        selected_tool = request.POST.get("tool", "mosint")
        top_sites = request.POST.get("top_sites", "100").strip()
        holehe_timeout = request.POST.get("holehe_timeout", "8").strip()
        no_recursion = request.POST.get("no_recursion") == "on"

        context["target"] = target
        context["selected_tool"] = selected_tool
        context["top_sites"] = top_sites
        context["holehe_timeout"] = holehe_timeout
        context["no_recursion"] = no_recursion

        if not target:
            context["parsed_lines"] = [
                {"text": "Please enter an email or username.", "kind": "error", "site": ""}
            ]
            return render(request, "dashboard/home.html", context)

        try:
            command = build_command(
                selected_tool=selected_tool,
                target=target,
                top_sites=top_sites,
                holehe_timeout=holehe_timeout,
                no_recursion=no_recursion,
            )

            if selected_tool == "mosint":
                if MOSINT_PATH != "mosint" and not os.path.exists(MOSINT_PATH):
                    context["parsed_lines"] = [
                        {"text": f"mosint.exe not found at: {MOSINT_PATH}", "kind": "error", "site": ""}
                    ]
                    return render(request, "dashboard/home.html", context)

                if not os.path.exists(CONFIG_PATH):
                    context["parsed_lines"] = [
                        {"text": f"Config file not found at: {CONFIG_PATH}", "kind": "error", "site": ""}
                    ]
                    return render(request, "dashboard/home.html", context)

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                encoding="utf-8",
                errors="replace",
            )

            raw_output = completed.stdout if completed.stdout.strip() else completed.stderr
            context["raw_output"] = raw_output

            if not raw_output.strip():
                context["parsed_lines"] = [
                    {"text": "No output returned.", "kind": "warning", "site": ""}
                ]
            else:
                cleaned_lines = clean_output(selected_tool, raw_output)
                context["parsed_lines"] = parse_lines_for_display(selected_tool, cleaned_lines)

        except subprocess.TimeoutExpired:
            context["parsed_lines"] = [
                {"text": "The selected tool took too long and was stopped.", "kind": "error", "site": ""}
            ]
        except FileNotFoundError as e:
            context["parsed_lines"] = [
                {"text": f"Tool not found: {e}", "kind": "error", "site": ""}
            ]
        except Exception as e:
            context["parsed_lines"] = [
                {"text": f"Error: {e}", "kind": "error", "site": ""}
            ]

    return render(request, "dashboard/home.html", context)


def build_command(selected_tool, target, top_sites, holehe_timeout, no_recursion):
    if selected_tool == "mosint":
        return [MOSINT_PATH, target, "--config", CONFIG_PATH]

    if selected_tool == "holehe":
        timeout_value = holehe_timeout if holehe_timeout.isdigit() else "8"
        return [HOLEHE_PATH, target, "--timeout", timeout_value]

    if selected_tool == "maigret":
        cmd = [MAIGRET_PATH, target]
        if top_sites.isdigit():
            cmd.extend(["--top-sites", top_sites])
        if no_recursion:
            cmd.append("--no-recursion")
        return cmd

    return ["cmd", "/c", "echo", "Unknown tool selected"]


def clean_output(selected_tool, raw_output):
    lines = raw_output.splitlines()
    cleaned = []

    for line in lines:
        line = line.replace("âœ", "").replace("â", "").replace("\x00", "").strip()

        if not line:
            continue

        if selected_tool == "mosint":
            lower = line.lower()
            if (
                "github.com/alpkeskin" in lower
                or lower.startswith("v3.")
                or lower == "mosint"
                or ("now:" in lower and "target email" not in lower)
            ):
                continue

        cleaned.append(line)

    return cleaned


def parse_lines_for_display(selected_tool, lines):
    parsed = []

    for line in lines:
        kind = classify_line(line)
        site = extract_site_name(line, selected_tool)

        parsed.append({
            "text": line,
            "kind": kind,
            "site": site,
        })

    return parsed


def classify_line(line):
    l = line.strip().lower()

    if any(token in l for token in ["error", "not found", "cannot", "failed", "traceback"]):
        return "error"

    if "[x]" in l or "rate limit" in l or "blocked" in l:
        return "blocked"

    if l.startswith("[+]") or l.startswith("+") or " exists" in l or " used" in l:
        return "positive"

    if l.startswith("[-]") or l.startswith("-") or " not exists" in l or " not used" in l:
        return "negative"

    if l.startswith("[?]") or "unknown" in l or "unclear" in l:
        return "warning"

    return "normal"


def extract_site_name(line, selected_tool):
    match = re.match(r"^\[\+\]\s+([A-Za-z0-9_.\- ]+)", line)
    if match:
        return match.group(1).strip()

    match = re.match(r"^\[\-\]\s+([A-Za-z0-9_.\- ]+)", line)
    if match:
        return match.group(1).strip()

    match = re.match(r"^\[x\]\s+([A-Za-z0-9_.\- ]+)", line)
    if match:
        return match.group(1).strip()

    site_keywords = [
        "Spotify", "Instagram", "Twitter", "Google", "IPApi",
        "HaveIBeenPwned", "Pastebin", "DNS", "Email", "Related Emails"
    ]
    for keyword in site_keywords:
        if keyword.lower() in line.lower():
            return keyword

    return ""