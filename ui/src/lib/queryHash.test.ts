import { describe, expect, it } from "vitest";
import { decodeQueryHash, encodeQueryHash } from "./queryHash";

describe("queryHash", () => {
  it("round-trips SQL including unicode", () => {
    const sql = "SELECT 'café' AS x FROM store.customers WHERE n > 1";
    expect(decodeQueryHash(encodeQueryHash(sql))).toBe(sql);
  });

  it("accepts a leading hash or a raw fragment", () => {
    const frag = encodeQueryHash("SELECT 1");
    expect(decodeQueryHash(frag)).toBe("SELECT 1");
    expect(decodeQueryHash(frag.slice(1))).toBe("SELECT 1");
  });

  it("returns null for missing or garbage hashes", () => {
    expect(decodeQueryHash("")).toBeNull();
    expect(decodeQueryHash("#other=abc")).toBeNull();
    expect(decodeQueryHash("#sql=%%%")).toBeNull();
  });
});
