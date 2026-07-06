import { describe, expect, it } from "vitest";
import { capitalize } from "./strings";

describe("capitalize", () => {
  it("uppercases the first letter", () => {
    expect(capitalize("hello")).toBe("Hello");
  });

  it("leaves the empty string alone", () => {
    expect(capitalize("")).toBe("");
  });
});
