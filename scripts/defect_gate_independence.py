#!/usr/bin/env python3
"""CI unlock: require a non-author GitHub APPROVED review.

Author-committed receipt.json cannot prove independent review. Local hooks still
validate that receipt; this script is the CI unlock for the required check
named "Zero-findings receipt".

Solo-maintainer exception: when the repo has no other human write collaborator
besides the PR author, non-author Approve is N/A and the check passes. Adding a
second write collaborator restores the hard non-author Approve requirement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple


def latest_review_state_by_user(reviews: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Return each reviewer's latest review state (API order is newest-first)."""
    latest: Dict[str, str] = {}
    for rev in reviews:
        user = (rev.get("user") or {}).get("login")
        state = str(rev.get("state") or "").upper()
        if not user or not state:
            continue
        if user in latest:
            continue
        latest[user] = state
    return latest


def non_author_approvers(
    reviews: Iterable[Dict[str, Any]], author: str
) -> List[str]:
    author_l = (author or "").strip().lower()
    out: List[str] = []
    for user, state in latest_review_state_by_user(reviews).items():
        if state != "APPROVED":
            continue
        if user.strip().lower() == author_l:
            continue
        out.append(user)
    return sorted(out)


def human_write_logins(collaborators: Iterable[Dict[str, Any]]) -> List[str]:
    """Human accounts with push/admin/maintain (excludes ``*[bot]``)."""
    out: List[str] = []
    for row in collaborators:
        login = str(row.get("login") or "").strip()
        if not login or login.lower().endswith("[bot]"):
            continue
        perms = row.get("permissions") if isinstance(row.get("permissions"), dict) else {}
        role = str(row.get("role_name") or "").strip().lower()
        if (
            perms.get("admin")
            or perms.get("maintain")
            or perms.get("push")
            or role in ("admin", "maintain", "write")
        ):
            out.append(login)
    return sorted(set(out))


def check_independence(
    *,
    author: str,
    reviews: Iterable[Dict[str, Any]],
    write_collaborators: Optional[Iterable[str]] = None,
) -> Tuple[bool, str]:
    if not (author or "").strip():
        return False, "pull request author is missing"
    author_l = author.strip().lower()
    approvers = non_author_approvers(reviews, author)
    if approvers:
        return True, f"non-author APPROVED by: {', '.join(approvers)}"
    if write_collaborators is not None:
        others = [
            u
            for u in write_collaborators
            if str(u or "").strip() and str(u).strip().lower() != author_l
        ]
        if not others:
            return (
                True,
                f"solo maintainer ({author}): non-author Approve N/A "
                "(no other human write collaborator)",
            )
    return (
        False,
        f"needs APPROVED review from someone other than {author} "
        "(author-signed receipt.json does not unlock CI)",
    )


def _gh_api(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aiplat-defect-gate-independence",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_event(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def resolve_pr_context(
    event: Dict[str, Any],
) -> Tuple[Optional[int], Optional[str]]:
    pr = event.get("pull_request")
    if isinstance(pr, dict):
        number = pr.get("number")
        author = ((pr.get("user") or {}).get("login")) if isinstance(pr.get("user"), dict) else None
        if number is not None:
            return int(number), str(author or "")
    # pull_request_review payload
    pr = event.get("pull_request")
    if not isinstance(pr, dict) and isinstance(event.get("review"), dict):
        # some payloads nest under pull_request already handled
        pass
    return None, None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        default=os.environ.get("GITHUB_EVENT_PATH", ""),
        help="path to GitHub event JSON (default: GITHUB_EVENT_PATH)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (default: GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=0,
        help="PR number override (tests / manual)",
    )
    parser.add_argument(
        "--author",
        default="",
        help="PR author login override (tests / manual)",
    )
    parser.add_argument(
        "--reviews-json",
        default="",
        help="path to reviews JSON array (offline / tests; skips API)",
    )
    parser.add_argument(
        "--collaborators-json",
        default="",
        help="path to collaborators JSON array (offline / tests; skips collaborators API)",
    )
    args = parser.parse_args(argv)

    # Never honor local bypass in CI independence check.
    if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
        if os.environ.get("AIPLAT_DEFECT_GATE", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            print(
                "defect_gate_independence: refusing AIPLAT_DEFECT_GATE bypass in CI",
                file=sys.stderr,
            )
            return 1

    author = (args.author or "").strip()
    pr_number = int(args.pr or 0)
    reviews: List[Dict[str, Any]] = []
    write_collaborators: Optional[List[str]] = None
    repo = (args.repo or "").strip()
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()

    if args.collaborators_json:
        with open(args.collaborators_json, encoding="utf-8") as f:
            collab_loaded = json.load(f)
        if not isinstance(collab_loaded, list):
            print(
                "defect_gate_independence: --collaborators-json must be a list",
                file=sys.stderr,
            )
            return 2
        write_collaborators = human_write_logins(
            [c for c in collab_loaded if isinstance(c, dict)]
        )

    if args.reviews_json:
        with open(args.reviews_json, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            print("defect_gate_independence: --reviews-json must be a list", file=sys.stderr)
            return 2
        reviews = [r for r in loaded if isinstance(r, dict)]
        if not author:
            print("defect_gate_independence: --author required with --reviews-json", file=sys.stderr)
            return 2
    else:
        event = _load_event(args.event or None)
        ev_pr, ev_author = resolve_pr_context(event)
        if not pr_number:
            pr_number = int(ev_pr or 0)
        if not author:
            author = (ev_author or "").strip()
        # pull_request_review events still have pull_request
        if not pr_number or not author:
            pr = event.get("pull_request")
            if isinstance(pr, dict):
                if not pr_number and pr.get("number") is not None:
                    pr_number = int(pr["number"])
                if not author:
                    author = str(((pr.get("user") or {}).get("login")) or "")

        if not pr_number or not author:
            print(
                "defect_gate_independence: cannot resolve PR number/author from event",
                file=sys.stderr,
            )
            return 2

        if not repo or not token:
            print(
                "defect_gate_independence: GITHUB_REPOSITORY and GITHUB_TOKEN required",
                file=sys.stderr,
            )
            return 2

        url = (
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
            f"?per_page=100"
        )
        try:
            loaded = _gh_api(url, token)
        except urllib.error.HTTPError as e:
            print(f"defect_gate_independence: reviews API failed: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"defect_gate_independence: reviews API error: {e}", file=sys.stderr)
            return 2
        if not isinstance(loaded, list):
            print("defect_gate_independence: unexpected reviews payload", file=sys.stderr)
            return 2
        reviews = [r for r in loaded if isinstance(r, dict)]

        if write_collaborators is None:
            collab_url = (
                f"https://api.github.com/repos/{repo}/collaborators"
                f"?affiliation=all&per_page=100"
            )
            try:
                collab_loaded = _gh_api(collab_url, token)
            except urllib.error.HTTPError as e:
                if getattr(e, "code", None) == 403:
                    # Default GITHUB_TOKEN may lack collaborators:read; owner
                    # match is the solo fallback (invitees still need Approve
                    # once listing is permitted).
                    try:
                        meta = _gh_api(f"https://api.github.com/repos/{repo}", token)
                    except Exception as meta_err:
                        print(
                            "defect_gate_independence: collaborators API 403 "
                            f"and repo meta failed: {meta_err}",
                            file=sys.stderr,
                        )
                        return 2
                    owner_login = str(
                        ((meta.get("owner") or {}).get("login")) or ""
                    ).strip()
                    if owner_login.lower() == author.strip().lower():
                        write_collaborators = [author]
                    else:
                        print(
                            "defect_gate_independence: collaborators API 403; "
                            "cannot verify solo maintainer",
                            file=sys.stderr,
                        )
                        return 2
                else:
                    print(
                        f"defect_gate_independence: collaborators API failed: {e}",
                        file=sys.stderr,
                    )
                    return 2
            except Exception as e:
                print(
                    f"defect_gate_independence: collaborators API error: {e}",
                    file=sys.stderr,
                )
                return 2
            else:
                if not isinstance(collab_loaded, list):
                    print(
                        "defect_gate_independence: unexpected collaborators payload",
                        file=sys.stderr,
                    )
                    return 2
                write_collaborators = human_write_logins(
                    [c for c in collab_loaded if isinstance(c, dict)]
                )

    ok, msg = check_independence(
        author=author,
        reviews=reviews,
        write_collaborators=write_collaborators,
    )
    if ok:
        print(f"defect_gate_independence: PASS {msg}")
        return 0
    print(f"defect_gate_independence: FAIL {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
