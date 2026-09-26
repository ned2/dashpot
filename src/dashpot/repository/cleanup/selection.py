"""Retain explicit Cleanup choices against refreshed evidence."""

from .targets import CleanupPreview, CleanupTarget


def primary_target(preview: CleanupPreview) -> CleanupTarget | None:
    """Identify a fixed subject only when the preview names a concrete target."""
    kind = "worktree" if preview.kind == "worktree" else "local-branch"
    target = next((target for target in preview.targets if target.kind == kind), None)
    if target is not None:
        if (
            preview.kind == "branch"
            and not target.available
            and any(
                other.kind == "remote-branch" and other.available
                for other in preview.targets
            )
        ):
            return None
        return target
    # A Branch row combines refs at multiple remotes. Keep the explicit choices
    # when observation has not selected one concrete remote Branch.
    if preview.kind == "branch" and len(preview.targets) == 1:
        return preview.targets[0]
    return None


def default_choices(preview: CleanupPreview) -> tuple[str, ...]:
    """The optional targets a first preview of a Worktree starts with selected.

    A Worktree prepared for Issue work is normally finished together with its
    Branch, so an available local Branch starts selected. The Branch at its
    push remote changes what other people see, so it starts selected only
    when the local Branch is available too and it is at the local Branch's
    tip: nothing reached the remote that the preview has not accounted for.
    A Branch preview selects nothing; a refreshed preview keeps choices by
    ``retained_choices`` instead.
    """
    if preview.kind != "worktree":
        return ()
    local = next(
        (target for target in preview.targets if target.kind == "local-branch"), None
    )
    return tuple(
        target.identity
        for target in preview.targets
        if target.requires is not None
        and target.available
        and local is not None
        and local.available
        and (target is local or target.expected == local.expected)
    )


def retained_choices(
    previous: CleanupPreview, refreshed: CleanupPreview, selected: tuple[str, ...]
) -> tuple[str, ...]:
    """Keep only optional choices whose identity and disclosed facts still agree."""
    retained = []
    for identity in selected:
        old, new = previous.target(identity), refreshed.target(identity)
        if (
            old is not None
            and new is not None
            and new.available
            and (
                old.model_dump(exclude={"observed_at"})
                == new.model_dump(exclude={"observed_at"})
            )
        ):
            retained.append(identity)
    return tuple(retained)
