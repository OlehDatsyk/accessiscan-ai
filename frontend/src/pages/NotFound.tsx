import { usePageTitle } from "../components/Layout";
import { ButtonLink, EmptyState } from "../components/ui";

export default function NotFound() {
  usePageTitle("Page not found");
  return (
    <div className="py-10">
      <h1 className="sr-only">Page not found</h1>
      <EmptyState title="We couldn't find that page" action={<ButtonLink to="/">Go to the dashboard</ButtonLink>}>
        The address may be mistyped, or the item may have been deleted.
      </EmptyState>
    </div>
  );
}
