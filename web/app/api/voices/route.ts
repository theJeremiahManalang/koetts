import { python } from "../../../lib/python";
export const runtime = "nodejs";
export async function GET() {
  try {
    const { stdout } = await python("web_audio.py", ["voices"]);
    return Response.json(JSON.parse(stdout));
  } catch (error) {
    console.error("Voice discovery failed:", error);
    return Response.json({ voices: [], error: "Windows speech voices are unavailable. Run this app on Windows with an installed speech voice." }, { status: 503 });
  }
}
