"""Shared metadata action responses, independent of artifact and project transport."""
from .workflow import identifier

METADATA_ACTIONS = frozenset({"submit", "requests", "delete", "work", "approve", "catalog", "published"})


def metadata_action(store, request):
    """Call only after the transport has authenticated and pinned the actor."""
    action = request.get("action")
    if action == "submit":
        return store.submit(request["reader"], request["title"], request["chapter"], request.get("notes", ""))
    if action == "requests":
        return store.list_reader(request["reader"])
    if action == "delete":
        store.delete(request["reader"], identifier(request["request_id"]))
        return {"deleted": True}
    if action == "work":
        work = store.list_work()
        for item in work:
            item["requests"] = store.work_requests(item["id"])
            item["link"] = store.get_link(item["id"])
            item.update(store.review_state(item["id"]))
            publication = store.publication(item["id"])
            item["publication_id"] = publication["id"] if publication else None
        return work
    if action == "approve":
        store.approve(identifier(request["work_id"]), request["actor"])
        return {"approved": True}
    if action == "catalog":
        return store.catalog()
    if action == "published":
        publication = store.publication(identifier(request["work_id"]))
        if not publication:
            raise ValueError("Publication not found")
        expected = identifier(request.get("publication_id", publication["id"]))
        if expected != publication["id"]:
            raise ValueError("Publication changed")
        return {"publication_id": expected}
    raise ValueError("Unsupported shared metadata action")
