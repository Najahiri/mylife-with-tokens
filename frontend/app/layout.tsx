import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'Bern · Research & Expertise Navigator',description:'Find research expertise and inspect the evidence behind every match.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
