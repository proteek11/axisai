import { redirect } from 'next/navigation';

// /admin has no content of its own — redirect to the main dashboard
export default function AdminRootPage() {
  redirect('/dashboard');
}
