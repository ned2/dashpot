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
