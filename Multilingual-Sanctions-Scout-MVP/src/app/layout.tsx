import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'Multilingual Sanctions Scout', description: 'Sanctions screening MVP for human review' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
