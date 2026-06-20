import './globals.css'

export const metadata = {
  title: 'MediBot Portal',
  description: 'Deployment-style clinical assistant for MediBot staff',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
