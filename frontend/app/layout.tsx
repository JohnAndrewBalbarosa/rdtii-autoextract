export const metadata = {
  title: "RDTII Trade Regulatory Analysis",
  description: "Reviewer / audit UI for the RDTII digital-trade regulatory analysis engine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
