import { Fragment, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

import type { AnalysisResponse } from '../../shared/api/types'
import { relativeTimeSince } from '../../shared/format/time'
import { useAnalysis } from '../dashboard/api'
import {
  ArrowRight,
  BarChart,
  Bolt,
  Briefcase,
  Clock,
  Database,
  DocSearch,
  Lightbulb,
  Shield,
  Target,
  TrendUp,
  type IconComponent,
} from './icons'

/**
 * The public landing page. Everything numeric — the jobs-analyzed count, the
 * top-skills ranking, and the freshness label — is read live from the same
 * /analysis endpoint the market dashboard uses (default, unscoped view), so
 * the marketing surface and the product never disagree.
 */
export function HomePage() {
  const { hash } = useLocation()
  const { data, isPending, isError } = useAnalysis({})

  // Honor deep links and cross-page "About" clicks (/#about).
  useEffect(() => {
    if (hash !== '#about') return
    document.getElementById('about')?.scrollIntoView({ behavior: 'smooth' })
  }, [hash])

  return (
    <div className="home">
      <Hero data={data} isPending={isPending} isError={isError} />
      <ValueSection />
      <AboutSection />
    </div>
  )
}

function Hero({
  data,
  isPending,
  isError,
}: {
  data: AnalysisResponse | undefined
  isPending: boolean
  isError: boolean
}) {
  return (
    <section className="hero">
      <div className="container">
        <div className="hero__grid">
          <div>
            <span className="eyebrow eyebrow--pill">Job market intelligence</span>
            <h1 className="hero__title">
              Understand the job market. Build a stronger career.
            </h1>
            <p className="hero__lead">
              Xcelsior analyzes thousands of job postings to help you discover in-demand
              skills, market trends, and the right opportunities for your goals.
            </p>

            <div className="hero__ctas">
              <Link className="cta-card cta-card--dark" to="/skills">
                <span className="cta-card__icon">
                  <BarChart size={22} />
                </span>
                <span className="cta-card__text">
                  <span className="cta-card__title">Explore Skills</span>
                  <span className="cta-card__sub">See market analytics</span>
                </span>
                <ArrowRight className="cta-card__arrow" size={18} />
              </Link>

              <Link className="cta-card" to="/jobs">
                <span className="cta-card__icon">
                  <Briefcase size={22} />
                </span>
                <span className="cta-card__text">
                  <span className="cta-card__title">Find Jobs</span>
                  <span className="cta-card__sub">Search matching jobs</span>
                </span>
                <ArrowRight className="cta-card__arrow" size={18} />
              </Link>
            </div>

            {data && (
              <p className="hero__meta">
                <span className="hero__meta-item">
                  <Clock size={15} />
                  {data.header.analyzed_jobs.toLocaleString()} jobs analyzed
                </span>
                <span className="hero__meta-dot" />
                <span>Updated {relativeTimeSince(data.computed_at)}</span>
              </p>
            )}
          </div>

          {isError ? <PulseUnavailable /> : isPending || !data ? <PulseSkeleton /> : <PulseCard data={data} />}
        </div>
      </div>
    </section>
  )
}

type TopSkill = { slug: string; name: string; count: number; share: number }

/** Flatten every category's technologies and rank by prevalence — the
 * broadest honest "what's in demand" read across the whole market. */
function topSkills(data: AnalysisResponse, limit = 5): TopSkill[] {
  return data.categories
    .flatMap((c) => c.technologies)
    .sort((a, b) => b.count - a.count)
    .slice(0, limit)
}

function PulseCard({ data }: { data: AnalysisResponse }) {
  const skills = topSkills(data)
  const max = skills[0]?.count ?? 1

  return (
    <div className="pulse">
      <div className="pulse__head">
        <span className="eyebrow">Live market snapshot</span>
        <p className="pulse__role">Top skills in demand</p>
        <span className="pulse__scope">Across all roles, nationwide</span>
      </div>

      <div className="pulse__rows">
        {skills.map((skill) => (
          <Link
            key={skill.slug}
            className="pulse-row"
            to={`/skills/${skill.slug}`}
            aria-label={`${skill.name}: ${skill.count.toLocaleString()} jobs`}
          >
            <span className="pulse-row__name">{skill.name}</span>
            <span className="bar">
              <span className="bar__fill" style={{ width: `${(skill.count / max) * 100}%` }} />
            </span>
            <span className="pulse-row__pct">{Math.round(skill.share * 100)}%</span>
            <span className="pulse-row__count">{skill.count.toLocaleString()} jobs</span>
          </Link>
        ))}
      </div>

      <div className="pulse__foot">
        <span className="pulse__foot-icon">
          <TrendUp size={20} />
        </span>
        <span>
          <strong>{data.header.analyzed_jobs.toLocaleString()}</strong> jobs analyzed
          <br />
          <span className="pulse__foot-sub">Updated {relativeTimeSince(data.computed_at)}</span>
        </span>
      </div>
    </div>
  )
}

function PulseSkeleton() {
  return <div className="pulse pulse--skeleton skeleton" aria-hidden="true" />
}

function PulseUnavailable() {
  return (
    <div className="pulse">
      <p className="pulse__role">Top skills in demand</p>
      <p className="muted">
        Market data is temporarily unavailable. Explore the{' '}
        <Link to="/skills">skills dashboard</Link> to try again.
      </p>
    </div>
  )
}

const VALUES: { icon: IconComponent; title: string; body: string }[] = [
  { icon: BarChart, title: 'Real Market Data', body: 'Insights from thousands of real job postings.' },
  { icon: Target, title: 'Relevant Insights', body: 'Skills, salaries, and trends that matter.' },
  { icon: Bolt, title: 'Always Updated', body: 'Fresh data added daily so you stay ahead.' },
  { icon: Shield, title: 'Built for Everyone', body: 'Students, professionals, and career changers.' },
]

function ValueSection() {
  return (
    <section className="value">
      <div className="container">
        <div className="value__grid">
          {VALUES.map(({ icon: Icon, title, body }) => (
            <div className="value-card" key={title}>
              <span className="icon-circle">
                <Icon size={22} />
              </span>
              <p className="value-card__title">{title}</p>
              <p className="value-card__body">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PIPELINE: { icon: IconComponent; title: string; body: string }[] = [
  {
    icon: Database,
    title: 'Collect',
    body: 'We gather job postings from multiple trusted sources across the web.',
  },
  {
    icon: DocSearch,
    title: 'Extract',
    body: 'Our pipeline identifies key details like skills, salaries, experience levels, and work arrangements.',
  },
  {
    icon: BarChart,
    title: 'Analyze',
    body: 'Thousands of postings are analyzed to uncover trends, in-demand skills, and market insights.',
  },
  {
    icon: Lightbulb,
    title: 'Deliver Insights',
    body: 'Clear, actionable data that helps you learn the right skills and find the right opportunities.',
  },
]

function AboutSection() {
  return (
    <section className="about" id="about">
      <div className="container">
        <div className="about__grid">
          <div>
            <span className="eyebrow eyebrow--pill">About Xcelsior</span>
            <h2 className="about__title">Built to bring clarity to the job market.</h2>
            <p className="about__lead">
              Xcelsior collects, processes, and analyzes thousands of job postings to reveal
              the skills, technologies, and trends shaping today&rsquo;s careers.
            </p>
          </div>

          <div className="pipeline" role="list">
            {PIPELINE.map(({ icon: Icon, title, body }, i) => (
              <Fragment key={title}>
                <div className="pipeline__step" role="listitem">
                  <span className="icon-circle">
                    <Icon size={22} />
                  </span>
                  <div className="pipeline__step-text">
                    <p className="pipeline__title">
                      {i + 1}. {title}
                    </p>
                    <p className="pipeline__body">{body}</p>
                  </div>
                </div>
                {i < PIPELINE.length - 1 && (
                  <span className="pipeline__arrow" aria-hidden="true">
                    <ArrowRight size={18} />
                  </span>
                )}
              </Fragment>
            ))}
          </div>
        </div>

        <div className="convert">
          <h2 className="convert__title">Ready to understand your market?</h2>
          <p className="convert__lead">Explore the skills employers are looking for.</p>
          <Link className="cta-card cta-card--dark" to="/skills">
            <span className="cta-card__icon">
              <BarChart size={20} />
            </span>
            <span className="cta-card__text">
              <span className="cta-card__title">Analyze Your Market</span>
            </span>
            <ArrowRight className="cta-card__arrow" size={18} />
          </Link>
        </div>
      </div>
    </section>
  )
}
