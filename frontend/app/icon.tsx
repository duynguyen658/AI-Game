import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    <div style={{ alignItems: "center", background: "#087e8b", color: "white", display: "flex", fontSize: 13, fontWeight: 700, height: "100%", justifyContent: "center", width: "100%" }}>CL</div>,
    size,
  );
}
