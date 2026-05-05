import { NextRequest } from "next/server";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

// Must be nodejs — edge runtime cannot reach localhost
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.json();

  // useChat sends { messages: Message[] } — we only forward the last user message
  const messages: { role: string; content: string }[] = body.messages ?? [];
  const lastUser = [...messages].reverse().find((m) => m.role === "user");

  if (!lastUser) {
    return new Response("No user message found", { status: 400 });
  }

  const fastapiRes = await fetch(`${FASTAPI_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: lastUser.content,
      model: body.model ?? "gpt-4o",
    }),
  });

  if (!fastapiRes.ok || !fastapiRes.body) {
    const text = await fastapiRes.text();
    return new Response(`FastAPI error: ${text}`, { status: fastapiRes.status });
  }

  // Pass the stream through verbatim — the x-vercel-ai-data-stream header
  // tells useChat to parse the 0:"token"\n frame format
  return new Response(fastapiRes.body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "x-vercel-ai-data-stream": "v1",
      "Cache-Control": "no-cache",
    },
  });
}
