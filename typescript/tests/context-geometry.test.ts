/**
 * NewContext geometry must fit the process-wide launch window (#164 / #190).
 * Twin of python/tests/test_context_geometry.py.
 */
import { describe, expect, it } from "vitest";
import {
	generateContextFingerprint,
	type LaunchWindow,
	loadPresets,
} from "../src/fingerprints.js";
import { attachLaunchWindow } from "../src/utils.js";
import { MODEL } from "./fpgen-setup.js";

const { NewContext } = await import("../src/sync_api.js");

const LAUNCH_WINDOW: LaunchWindow = {
	outer: [1366, 728],
	inner: [1366, 643],
	screen: [1366, 768],
};
const NO_INNER: LaunchWindow = { ...LAUNCH_WINDOW, inner: [null, null] };

function fakeBrowser(launchWindow?: unknown) {
	const browser: Record<string, any> = {
		version: () => "156.0",
		_camoufoxLaunchWindow: launchWindow,
		newContext: async (options: Record<string, any>) => {
			browser.options = options;
			return { addInitScript: async () => {} };
		},
	};
	return browser;
}

describe.skipIf(!MODEL.ok)("NewContext fits the launch window", () => {
	it("the viewport is the launch inner and the screen holds the window", () => {
		const fingerprint = generateContextFingerprint({
			os: "windows",
			launch_window: LAUNCH_WINDOW,
		});
		expect(fingerprint.context_options.viewport).toEqual({
			width: 1366,
			height: 643,
		});
		const screenWidth = fingerprint.config["screen.width"];
		const screenHeight = fingerprint.config["screen.height"];
		expect(screenWidth >= LAUNCH_WINDOW.outer[0]).toBe(true);
		expect(screenHeight >= LAUNCH_WINDOW.outer[1]).toBe(true);
		expect(fingerprint.init_script).toContain(
			`w.setScreenDimensions(${screenWidth}, ${screenHeight})`,
		);
	});

	it.each([
		"windows",
		"macos",
		"linux",
	])("%s: no launch inner keeps the preset viewport inside the outer window and its scale factor", (os) => {
		const [outerWidth, outerHeight] = NO_INNER.outer;
		const presets = loadPresets()?.presets?.[os] ?? [];
		const small = presets.find(
			(preset) =>
				preset.screen.width < outerWidth || preset.screen.height < outerHeight,
		);
		expect(small, `no ${os} preset needs clamping`).toBeDefined();
		let clamped = 0;
		for (const preset of [presets[0], small]) {
			const options = generateContextFingerprint({
				preset,
				launch_window: NO_INNER,
			}).context_options;
			const viewport = options.viewport;
			expect("no_viewport" in options).toBe(false);
			expect(viewport.width <= outerWidth).toBe(true);
			expect(viewport.height <= outerHeight).toBe(true);
			expect(options.deviceScaleFactor).toBe(
				preset.screen.devicePixelRatio ?? undefined,
			);
			if (
				viewport.width !== preset.screen.width ||
				viewport.height !== Math.max(preset.screen.height - 28, 600)
			) {
				clamped++;
			}
		}
		expect(clamped, "no draw exercised the clamp").toBeGreaterThan(0);
	});

	it("NewContext passes the launch window, and an explicit viewport wins", async () => {
		const browser = fakeBrowser(NO_INNER);
		await NewContext(browser as any, { os: "windows" });
		expect(browser.options.viewport.width).toBeLessThanOrEqual(
			NO_INNER.outer[0],
		);
		expect(browser.options.viewport.height).toBeLessThanOrEqual(
			NO_INNER.outer[1],
		);
		await NewContext(browser as any, {
			os: "windows",
			viewport: { width: 800, height: 600 },
		});
		expect(browser.options.viewport).toEqual({ width: 800, height: 600 });
	});

	it("a malformed launch window behaves as none", () => {
		const shape = (launchWindow: unknown) => {
			const options = generateContextFingerprint({
				os: "windows",
				launch_window: launchWindow as LaunchWindow,
			}).context_options;
			return ["viewport", "deviceScaleFactor"].map(
				(key) => options[key] !== undefined,
			);
		};
		const baseline = shape(null);
		for (const malformed of [
			{ outer: [1, 2] },
			{ outer: 1, inner: 2, screen: 3 },
			{ outer: ["wide", "tall"], inner: [null, null], screen: [1920, 1080] },
			"not a launch window",
		]) {
			expect(shape(malformed)).toEqual(baseline);
		}
	});

	it("an explicit no-viewport drops the generated viewport and scale factor", async () => {
		const preset = loadPresets()?.presets?.macos?.find(
			(candidate) => candidate.screen.devicePixelRatio === 2,
		);
		expect(preset).toBeDefined();
		const browser = fakeBrowser(NO_INNER);
		await NewContext(browser as any, { preset });
		expect(browser.options.deviceScaleFactor).toBe(2);
		for (const disabled of [{ noViewport: true }, { viewport: null }]) {
			await NewContext(browser as any, { preset, ...disabled });
			expect(browser.options.viewport).toBeNull();
			expect("deviceScaleFactor" in browser.options).toBe(false);
			expect("noViewport" in browser.options).toBe(false);
		}
	});
});

describe("attachLaunchWindow", () => {
	it("reads the launch config and defaults the outer window", () => {
		const config = {
			"window.innerWidth": 1000,
			"window.innerHeight": 600,
			"screen.width": 1920,
			"screen.height": 1080,
		};
		const browser: Record<string, any> = {};
		attachLaunchWindow(browser, {
			env: { CAMOU_CONFIG_1: JSON.stringify(config) },
		});
		expect(browser._camoufoxLaunchWindow).toEqual({
			outer: [1280, 1040],
			inner: [1000, 600],
			screen: [1920, 1080],
		});
	});

	it("ignores a malformed launch config", () => {
		const browser: Record<string, any> = {};
		expect(() =>
			attachLaunchWindow(browser, { env: { CAMOU_CONFIG_1: "{" } }),
		).not.toThrow();
		expect(browser._camoufoxLaunchWindow).toBeUndefined();
	});
});
