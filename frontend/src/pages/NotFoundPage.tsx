import { Link } from "react-router-dom";

export function NotFoundPage() {
  return <div className="page not-found"><span aria-hidden="true">404</span><h1>This route is outside the academy map.</h1><p>Return home or browse the structured curriculum.</p><div className="button-row"><Link className="button button-primary" to="/">Go home</Link><Link className="button button-secondary" to="/curriculum">Browse curriculum</Link></div></div>;
}

