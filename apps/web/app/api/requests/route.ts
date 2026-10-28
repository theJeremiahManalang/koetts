import { FieldValue, Timestamp } from "firebase-admin/firestore";
import {
    getAdminAuth,
    getAdminFirestore,
} from "../../../features/identity/firebase-admin";

export const runtime = "nodejs";

export async function POST(request: Request) {
    const authorization = request.headers.get("authorization");

    if (!authorization?.startsWith("Bearer ")) {
        return Response.json(
        { error: "Please sign in first." },
        { status: 401 },
        );
    }

    let userId: string;

    try {
        const token = authorization.slice("Bearer ".length);
        const decoded = await getAdminAuth().verifyIdToken(token, true);
        userId = decoded.uid;
    } catch {
        return Response.json(
        { error: "Could not verify your account. Please sign in again." },
        { status: 401 },
        );
    }

    let body: unknown;

    try {
        body = await request.json();
    } catch {
        return Response.json(
        { error: "Invalid JSON." },
        { status: 400 },
        );
    }

    if (!body || typeof body !== "object" || Array.isArray(body)) {
        return Response.json(
        { error: "Invalid request data." },
        { status: 400 },
        );
    }

    const input = body as Record<string, unknown>;
    const mangaTitle =
        typeof input.mangaTitle === "string" ? input.mangaTitle.trim() : "";
    const chapterText =
        typeof input.chapter === "string" ? input.chapter.trim() : "";
    const notes =
        typeof input.notes === "string" ? input.notes.trim() : "";

    if (
        mangaTitle.length < 1 ||
        mangaTitle.length > 200 ||
        !/^[0-9]{1,4}$/.test(chapterText) ||
        typeof input.notes !== "string" ||
        notes.length > 2000
    ) {
        return Response.json(
        {
            error:
            "Use a title of 1–200 characters, a chapter of 1–4 digits, " +
            "and notes of no more than 2,000 characters.",
        },
        { status: 400 },
        );
    }

    const chapter = Number(chapterText);

    try {
        const document = await getAdminFirestore()
        .collection("manga_requests")
        .add({
            userId,
            mangaTitle,
            chapter,
            notes,
            status: "submitted",
            createdAt: FieldValue.serverTimestamp(),
        });

        return Response.json({ id: document.id }, { status: 201 });
    } catch (error) {
        console.error("Failed to save manga request:", error);

        return Response.json(
        { error: "Could not save your request. Please try again." },
        { status: 500 },
        );
    }
}

export async function GET(request: Request) {
    const authorization = request.headers.get("authorization");

    if (!authorization?.startsWith("Bearer ")) {
        return Response.json(
        { error: "Please sign in first." },
        { status: 401 },
        );
    }

    let userId: string;

    try {
        const token = authorization.slice("Bearer ".length);
        const decoded = await getAdminAuth().verifyIdToken(token, true);
        userId = decoded.uid;
    } catch {
        return Response.json(
        { error: "Could not verify your account. Please sign in again." },
        { status: 401 },
        );
    }

    try {
        const snapshot = await getAdminFirestore()
        .collection("manga_requests")
        .where("userId", "==", userId)
        .get();

        const requests = snapshot.docs.map(document => {
        const data = document.data();

        return {
            id: document.id,
            mangaTitle: data.mangaTitle,
            chapter: data.chapter,
            notes: data.notes,
            status:
            typeof data.status === "string"
                ? data.status.toUpperCase()
                : "pending",
            createdAt:
            data.createdAt instanceof Timestamp
                ? data.createdAt.toDate().toISOString()
                : "",
        };
        });

        requests.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

        return Response.json(
        { requests },
        { headers: { "Cache-Control": "private, no-store" } },
        );
    } catch (error) {
        console.error("Failed to load manga requests:", error);

        return Response.json(
        { error: "Could not load your requests. Please try again." },
        { status: 500 },
        );
    }
}