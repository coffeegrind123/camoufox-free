/**
 * A context whose proxy is set a second time keeps its storage.
 *
 * Playwright sends Browser.setContextProxy once, when a context is created
 * with a proxy; a client driving the protocol can send it again to move the
 * context to another proxy. Juggler then has to drop the context's cached
 * proxy login, and it did that with clear-origin-attributes-data: Gecko's
 * "forget this context" signal. sessionStorage went with it (null after a
 * reload) and so did push subscriptions, which a page notices mid-session.
 * proxy-auth-isolation.patch gives the auth cache a topic of its own.
 *
 * Opt-in, it needs a browser binary:
 *
 *   CAMOUFOX_E2E=1 CAMOUFOX_EXECUTABLE=/path/to/camoufox-bin pnpm test tests/context-proxy-reset.test.ts
 */
import * as http from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const EXECUTABLE = process.env.CAMOUFOX_EXECUTABLE ?? "";
const ENABLED = process.env.CAMOUFOX_E2E === "1" && Boolean(EXECUTABLE);

const PAGE = "<!doctype html><title>ok</title><body>ok</body>";

/** A forward proxy that answers every plain-HTTP request itself, naming itself. */
function answeringProxy(name: string): Promise<http.Server> {
	const server = http.createServer((_req, res) => {
		res.writeHead(200, {
			"Content-Type": "text/html",
			"X-Proxy": name,
			"Cache-Control": "no-store",
		});
		res.end(PAGE);
	});
	return new Promise((resolve) =>
		server.listen(0, "127.0.0.1", () => resolve(server)),
	);
}

const port = (server: http.Server) => (server.address() as AddressInfo).port;

describe.runIf(ENABLED)("a second setContextProxy", () => {
	let proxyA: http.Server;
	let proxyB: http.Server;

	beforeAll(async () => {
		proxyA = await answeringProxy("A");
		proxyB = await answeringProxy("B");
	});

	afterAll(() => {
		proxyA?.close();
		proxyB?.close();
	});

	it("moves the context to the new proxy and keeps its storage", async () => {
		const { Camoufox } = await import("../src/sync_api.js");
		const browser = await Camoufox({
			executable_path: EXECUTABLE,
			headless: true,
			i_know_what_im_doing: true,
		});
		try {
			const context = await browser.newContext({
				proxy: { server: `http://127.0.0.1:${port(proxyA)}` },
			});
			const page = await context.newPage();
			const url = "http://storage.proxy-reset.test/";
			const first = await page.goto(url);
			expect(first?.headers()["x-proxy"]).toBe("A");
			await page.evaluate(() => {
				sessionStorage.setItem("s", "kept");
				localStorage.setItem("l", "kept");
				document.cookie = "c=kept; path=/";
			});

			// The second call goes on the protocol, as a client driving Juggler
			// sends it; Playwright's API has no way to re-set a context's proxy.
			const impl = (context as any)._connection.toImpl(context);
			await impl._browser.session.send("Browser.setContextProxy", {
				browserContextId: impl._browserContextId,
				type: "http",
				host: "127.0.0.1",
				port: port(proxyB),
				bypass: [],
			});

			const again = await page.reload();
			expect(again?.headers()["x-proxy"]).toBe("B");
			const seen = await page.evaluate(() => ({
				session: sessionStorage.getItem("s"),
				local: localStorage.getItem("l"),
				cookie: document.cookie,
			}));
			expect(seen).toEqual({
				session: "kept",
				local: "kept",
				cookie: "c=kept",
			});
		} finally {
			await browser.close();
		}
	}, 120_000);
});
