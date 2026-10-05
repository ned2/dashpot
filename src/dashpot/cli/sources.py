"""``dashpot issue`` and ``dashpot pr``: ask the configured Project source, writing nothing."""

from __future__ import annotations

from typing import Annotated, Literal

from cyclopts import App, Parameter, validators

from ..composition import command_query_source
from ..core.working_directory import current_directory
from ..issues.issue_resolution import describe_issue, show_issue
from ..queries.pages import Lifecycle, PageObservation, QueryRequest
from ..serialization import issue_document, list_page_document, render_json
from .shared import IssueHint, JsonOutput, Timeout, print_lines

issue = App(
    name="issue",
    help=(
        "Resolve Issues through the configured Issue Source.\n\n"
        "Source-neutral: the same Issue Hints work for a GitHub Project and a "
        "Local Issue Markdown Project, and nothing is written."
    ),
)


@issue.command(name="show")
def issue_show(
    reference: IssueHint,
    /,
    *,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Resolve one Issue Hint and print the Issue Profile."""
    found = show_issue(current_directory(), reference, timeout=timeout)
    if json_output:
        print(render_json(issue_document(found)))
    else:
        print_lines(describe_issue(found))
    return 0


pr = App(name="pr", help="Query Pull Requests through the configured Project source.")


def _list_page(
    kind: Literal["issues", "pull-requests"],
    query: str,
    state: Lifecycle,
    page_size: int,
    cursor: str | None,
    compact: bool,
    timeout: float,
) -> int:
    """Emit one Query Page and the Project Totals its request counted.

    The page's Diagnostics carry what the source reports about itself
    beside it, such as a rate limit running low.
    """
    source = command_query_source(current_directory(), timeout=timeout)
    observation = source.query_page(
        QueryRequest(
            kind=kind, query=query, state=state, page_size=page_size, cursor=cursor
        )
    )
    page = observation.page
    reported = page.model_copy(
        update={"diagnostics": (*page.diagnostics, *source.source_diagnostics())}
    )
    print(
        render_json(
            list_page_document(PageObservation(reported, observation.totals)),
            compact=compact,
        )
    )
    return 0


_PageSize = Annotated[
    int,
    Parameter(
        validator=validators.Number(gte=1, lte=100),
        show_default=False,
        help="the most records the page holds, from 1 to 100 (50 when omitted)",
    ),
]
_Cursor = Annotated[
    str | None,
    Parameter(
        help=(
            "the nextCursor of the previous page, to continue the same query, "
            "lifecycle and page size"
        )
    ),
]
# A Query Page has no line rendering: the list commands always print JSON,
# and accept --json so a script that passes it keeps working.
_ListJson = Annotated[
    bool,
    Parameter(
        name="--json",
        show_default=False,
        help="accepted and ignored: the page is always printed as JSON",
    ),
]
_CompactJson = Annotated[
    bool,
    Parameter(show_default=False, help="omit JSON indentation"),
]


@issue.command(name="list")
def issue_list(
    *,
    query: Annotated[
        str,
        Parameter(
            show_default=False,
            help=(
                "the search: GitHub advanced search syntax for a GitHub Issue "
                "Source, local text for a Local Issue Markdown one"
            ),
        ),
    ] = "",
    state: Lifecycle = "open",
    page_size: _PageSize = 50,
    cursor: _Cursor = None,
    json_output: _ListJson = False,
    compact_json: _CompactJson = False,
    timeout: Timeout = 10.0,
) -> int:
    """Print one Issue Query Page, and the Project Totals it counted, as JSON.

    ``--state ready`` lists Ready Issues: open, with no Open Blocker.
    """
    return _list_page("issues", query, state, page_size, cursor, compact_json, timeout)


@pr.command(name="list")
def pr_list(
    *,
    query: Annotated[
        str,
        Parameter(
            show_default=False, help="the search, in GitHub advanced search syntax"
        ),
    ] = "",
    state: Literal["open", "closed", "all"] = "open",
    page_size: _PageSize = 50,
    cursor: _Cursor = None,
    json_output: _ListJson = False,
    compact_json: _CompactJson = False,
    timeout: Timeout = 10.0,
) -> int:
    """Print one Pull Request Query Page, and the Project Totals it counted, as JSON."""
    return _list_page(
        "pull-requests", query, state, page_size, cursor, compact_json, timeout
    )
