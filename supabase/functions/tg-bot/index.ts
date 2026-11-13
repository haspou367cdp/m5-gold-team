// Supabase Edge Function entry (Deno). Logic: app.js + lib.js. Deployed with verify_jwt=false:
// Telegram is authenticated by its secret_token header, GitHub by its OIDC token.
import { makeApp } from "./app.js";

const app = makeApp({
  url: Deno.env.get("SUPABASE_URL")!,
  key: Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
});
Deno.serve((req: Request) => app(req));
