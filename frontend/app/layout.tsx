import "./globals.css";
import type { Metadata } from "next";
import Nav from "./components/Nav";

export const metadata: Metadata = {
  title: "AI Trading Platform",
  description: "Compliant, single-user AI trading platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
