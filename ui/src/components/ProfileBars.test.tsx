import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ProfileBars from "./ProfileBars";

describe("ProfileBars", () => {
  it("renders frequency bars for a column", () => {
    const { getByText } = render(
      <ProfileBars top={{ region: [["US", 3], ["EU", 1]] }} />,
    );
    expect(getByText("US")).toBeTruthy();
    expect(getByText("EU")).toBeTruthy();
  });

  it("hides values for a masked (PII) column under Agent view", () => {
    const { getByText, queryByText } = render(
      <ProfileBars top={{ email: [["a@x.com", 2]] }} masked={new Set(["email"])} />,
    );
    expect(getByText(/hidden \(PII\)/)).toBeTruthy();
    expect(queryByText("a@x.com")).toBeNull();
  });
});
