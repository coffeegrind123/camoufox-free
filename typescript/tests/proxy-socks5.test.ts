/**
 * SOCKS5 credentials travel through the launch environment because Playwright's
 * driver rejects them in the public proxy options.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isolateLaunch, restoreDeps, utils } from "./launch-host.js";

const impit = vi.hoisted(() => ({ requests: 0 }));

vi.mock("impit", () => ({
	Impit: class {
		async fetch(): Promise<never> {
			impit.requests++;
			throw new Error("geo lookup must not run");
		}
	},
}));

const { InvalidProxy } = await import("../src/exceptions.js");
const { PROXY_CREDENTIALS_ENV, splitSocksCredentials } = await import(
	"../src/ip.js"
);
const { NewContext } = await import("../src/sync_api.js");

function launch(
	proxy: any,
	env: Record<string, any>,
	extra: Record<string, any> = {},
) {
	return utils.launchOptions({
		block_webgl: true,
		headless: true,
		i_know_what_im_doing: true,
		proxy,
		env,
		...extra,
	});
}

function fakeBrowser() {
	let contexts = 0;
	let options: Record<string, any> | undefined;
	const browser = {
		version: () => "152.0.4",
		newContext: async (value: Record<string, any>) => {
			contexts++;
			options = value;
			return { addInitScript: async () => undefined };
		},
	};
	return {
		browser: browser as any,
		contexts: () => contexts,
		options: () => options,
	};
}

beforeEach(() => {
	restoreDeps();
	isolateLaunch();
	impit.requests = 0;
});

afterEach(() => {
	restoreDeps();
});

describe("splitSocksCredentials", () => {
	it("decodes URL credentials and removes them from the proxy", () => {
		const [proxy, credentials] = splitSocksCredentials({
			server: "socks5://us%40er%23:p%23ss%2Fw%3Frd%2541@Proxy.Example.com:1080",
			bypass: ".internal.example",
		});

		expect(proxy).toEqual({
			server: "socks5://proxy.example.com:1080",
			bypass: ".internal.example",
		});
		expect(credentials).toEqual({
			"proxy.example.com:1080": {
				username: "us@er#",
				password: "p#ss/w?rd%41",
			},
		});
	});

	it("gives explicit username and password fields precedence", () => {
		const [proxy, credentials] = splitSocksCredentials({
			server: "SoCkS5H://url-user:url-pass@Proxy.Example.com:1080",
			username: "field-user",
			password: "field-pass",
		});

		expect(proxy).toEqual({ server: "socks5://proxy.example.com:1080" });
		expect(credentials).toEqual({
			"proxy.example.com:1080": {
				username: "field-user",
				password: "field-pass",
			},
		});
	});

	it("normalizes unauthenticated socks5h to socks5", () => {
		const [proxy, credentials] = splitSocksCredentials({
			server: "SOCKS5H://Proxy.Example.com:1080",
		});

		expect(proxy).toEqual({ server: "socks5://proxy.example.com:1080" });
		expect(credentials).toBeUndefined();
	});

	it("brackets an IPv6 server and omits brackets from its map key", () => {
		const [proxy, credentials] = splitSocksCredentials({
			server: "socks5h://user:pass@[2001:DB8::1]:1080",
		});

		expect(proxy).toEqual({ server: "socks5://[2001:db8::1]:1080" });
		expect(credentials).toEqual({
			"2001:db8::1:1080": { username: "user", password: "pass" },
		});
	});

	it("leaves HTTP proxy credentials to Playwright", () => {
		const proxy = {
			server: "http://proxy.example.com:8080",
			username: "user",
			password: "pass",
		};

		expect(splitSocksCredentials(proxy)).toEqual([proxy, undefined]);
	});

	it.each([
		[{ server: "socks5://" }, /host/],
		[{ server: "socks5:proxy.example.com:1080" }, /Invalid proxy/],
		[{ server: "//proxy.example.com:1080" }, /Invalid proxy/],
		[{ server: "socks5://proxy.example.com:not-a-port" }, /port/],
		[{ server: "socks5://proxy.example.com:70000" }, /port/],
		[{ server: "socks5://proxy.example.com:0" }, /port/],
		[{ server: "socks5://proxy.example.com:" }, /port/],
		[{ server: "socks5://:pass@proxy.example.com:1080" }, /username/],
		[{ server: "socks5://user:pass@proxy.example.com" }, /port/],
		[{ server: "socks5://proxy.example.com" }, /port/],
		[
			{
				server: "socks5://proxy.example.com",
				username: "user",
				password: "pass",
			},
			/port/,
		],
		[
			{
				server: "socks5://proxy.example.com:1080",
				username: "",
				password: "pass",
			},
			/username/,
		],
		[{ server: "socks5://proxy.example.com:1080/path" }, /Invalid proxy/],
	])("rejects %o", (proxy, message) => {
		expect(() => splitSocksCredentials(proxy as any)).toThrow(InvalidProxy);
		expect(() => splitSocksCredentials(proxy as any)).toThrow(message);
	});
});

describe("launchOptions SOCKS5 credentials", () => {
	it("sanitizes the proxy and injects the endpoint map", async () => {
		const options = await launch(
			{
				server: "socks5h://embedded-user:embedded-pass@Proxy.Example.com:1080",
				username: "launch-user",
				password: "launch-pass",
			},
			{ HOME: "/tmp/camoufox-proxy-socks5" },
		);

		expect(options.proxy).toEqual({
			server: "socks5://proxy.example.com:1080",
		});
		expect(JSON.parse(options.env[PROXY_CREDENTIALS_ENV])).toEqual({
			"proxy.example.com:1080": {
				username: "launch-user",
				password: "launch-pass",
			},
		});
	});

	it("keeps an explicitly supplied credentials environment", async () => {
		const declared = JSON.stringify({
			"proxy-a.example.com:1080": {
				username: "user-a",
				password: "pass-a",
			},
			"proxy-b.example.com:1080": {
				username: "user-b",
				password: "pass-b",
			},
		});
		const options = await launch(
			{
				server: "socks5://proxy-c.example.com:1080",
				username: "user-c",
				password: "pass-c",
			},
			{
				CAMOU_PROXY_CREDENTIALS: declared,
				UNCHANGED: "value",
			},
		);

		expect(options.proxy).toEqual({
			server: "socks5://proxy-c.example.com:1080",
		});
		expect(options.env[PROXY_CREDENTIALS_ENV]).toBe(declared);
		expect(options.env.UNCHANGED).toBe("value");
	});

	it("uses the sanitized endpoint and selected credentials for geo lookup", async () => {
		let lookup: string | undefined;
		utils.utilsDeps.publicIp = async (proxy?: string) => {
			lookup = proxy;
			return "203.0.113.7";
		};
		utils.utilsDeps.getGeolocation = (async () => ({
			asConfig: () => ({
				timezone: "UTC",
				"locale:language": "en",
				"locale:region": "US",
			}),
		})) as any;

		await launch(
			{
				server: "socks5h://url-user:url-pass@Proxy.Example.com:1080",
				username: "field@user",
				password: "p@ss/word",
			},
			{ HOME: "/tmp/camoufox-proxy-socks5" },
			{ geoip: true },
		);

		expect(lookup).toBe(
			"socks5://field%40user:p%40ss%2Fword@proxy.example.com:1080",
		);
	});

	it("does not inject credentials for an unauthenticated proxy", async () => {
		const options = await launch(
			{ server: "socks5h://proxy.example.com:1080" },
			{ HOME: "/tmp/camoufox-proxy-socks5" },
		);

		expect(options.proxy).toEqual({
			server: "socks5://proxy.example.com:1080",
		});
		expect(options.env).not.toHaveProperty(PROXY_CREDENTIALS_ENV);
	});

	it("rejects a SOCKS5 proxy without an explicit port before launch assembly", async () => {
		const launching = launch(
			{ server: "socks5h://proxy.example.com" },
			{ HOME: "/tmp/camoufox-proxy-socks5" },
		);

		await expect(launching).rejects.toThrow(InvalidProxy);
		await expect(launching).rejects.toThrow(/explicit port/);
	});
});

describe("NewContext SOCKS5 credentials", () => {
	it.each([
		{ server: "socks5://user:pass@proxy.example.com:1080" },
		{
			server: "socks5h://proxy.example.com:1080",
			username: "user",
			password: "pass",
		},
	])("fails closed before the geo lookup for %o", async (proxy) => {
		const { browser, contexts } = fakeBrowser();

		const created = NewContext(browser, { os: "linux", proxy });

		await expect(created).rejects.toThrow(InvalidProxy);
		await expect(created).rejects.toThrow(/CAMOU_PROXY_CREDENTIALS/);
		expect(impit.requests).toBe(0);
		expect(contexts()).toBe(0);
	});

	it("skips the lookup when the caller supplies all four geo values", async () => {
		const { browser, contexts, options } = fakeBrowser();

		await NewContext(browser, {
			os: "linux",
			proxy: { server: "socks5h://proxy.example.com:1080" },
			webrtc_ip: "198.51.100.1",
			timezoneId: "UTC",
			locale: "en-US",
			geolocation: { latitude: 40.7128, longitude: -74.006 },
		} as any);

		expect(impit.requests).toBe(0);
		expect(contexts()).toBe(1);
		expect(options()?.proxy).toEqual({
			server: "socks5://proxy.example.com:1080",
		});
	});
});
