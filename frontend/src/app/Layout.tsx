import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { useCurrentUser, useLogout } from '../features/auth/api'
import { BrandMark, Close, Menu } from '../features/home/icons'

export function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const isHome = location.pathname === '/'
  const close = () => setMenuOpen(false)

  return (
    <div className="layout">
      <header className={`site-header${menuOpen ? ' nav--open' : ''}`}>
        <div className="nav-inner">
          <Link to="/" className="brand" onClick={close}>
            <BrandMark className="brand__mark" />
            Xcelsior
          </Link>

          <button
            type="button"
            className="nav-toggle"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <Close size={22} /> : <Menu size={22} />}
          </button>

          <nav className="site-nav" onClick={close}>
            <NavLink to="/skills">Skills</NavLink>
            <NavLink to="/jobs">Jobs</NavLink>
            <AboutLink onNavigate={close} />
          </nav>

          <AuthNav onNavigate={close} />
        </div>
      </header>

      <main>
        {isHome ? (
          <Outlet />
        ) : (
          <div className="container--app">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}

/** "About" is a section of the homepage, not a route. On the homepage we
 * smooth-scroll to it; from anywhere else we route home with the hash and
 * the homepage scrolls itself into place on arrival. */
function AboutLink({ onNavigate }: { onNavigate: () => void }) {
  const location = useLocation()

  const onClick = (event: React.MouseEvent) => {
    onNavigate()
    if (location.pathname === '/') {
      event.preventDefault()
      document.getElementById('about')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <Link to="/#about" className="nav-link" onClick={onClick}>
      About
    </Link>
  )
}

/** The right side of the nav reflects auth state (M10): anonymous visitors
 * see Log in / Sign up; signed-in users see their personal surface plus a
 * logout control. Personal links are hidden (not just gated) when logged out,
 * so the public browse experience stays uncluttered. */
function AuthNav({ onNavigate }: { onNavigate: () => void }) {
  const { data: user, isPending } = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()

  if (isPending) return <div className="nav-auth" />

  if (!user) {
    return (
      <div className="nav-auth" onClick={onNavigate}>
        <NavLink to="/login" className="nav-link">
          Log in
        </NavLink>
        <NavLink to="/signup" className="btn btn--primary btn--pill">
          Sign up
        </NavLink>
      </div>
    )
  }

  return (
    <div className="nav-auth">
      <NavLink to="/saved" className="nav-link" onClick={onNavigate}>
        Saved
      </NavLink>
      <NavLink to="/profile" className="nav-link" onClick={onNavigate}>
        Profile
      </NavLink>
      <span className="nav-user" title={user.email}>
        {user.email}
      </span>
      <button
        type="button"
        className="btn btn--link nav-logout"
        onClick={() => {
          onNavigate()
          logout.mutate(undefined, { onSuccess: () => navigate('/') })
        }}
        disabled={logout.isPending}
      >
        Log out
      </button>
    </div>
  )
}
