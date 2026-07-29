import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { JobFilters } from '../../shared/filters'
import { FilterPanel } from './FilterPanel'

function renderPanel(filters: JobFilters = {}) {
  const onChange = vi.fn()
  render(<FilterPanel filters={filters} meta={undefined} onChange={onChange} />)
  return onChange
}

describe('FilterPanel employment type', () => {
  it('offers internships as their own filter, separate from full-time', async () => {
    renderPanel()

    const select = screen.getByLabelText('Employment type')
    const options = Array.from(select.querySelectorAll('option')).map((o) => o.value)
    expect(options).toEqual(['', 'full_time', 'part_time', 'internship', 'contract', 'temporary'])
  })

  it('writes the selected type into the filter state', async () => {
    const onChange = renderPanel({ q: 'python' })

    await userEvent.selectOptions(screen.getByLabelText('Employment type'), 'internship')

    // Existing filters survive; only employment_type is added.
    expect(onChange).toHaveBeenCalledWith({ q: 'python', employment_type: 'internship' })
  })

  it('shows the active type as a removable chip', async () => {
    const onChange = renderPanel({ employment_type: 'internship' })

    expect(screen.getByLabelText('Employment type')).toHaveValue('internship')
    await userEvent.click(screen.getByRole('button', { name: /internship/i }))

    expect(onChange).toHaveBeenCalledWith({ employment_type: undefined })
  })

  it('leaves the type untouched when another filter changes', async () => {
    const onChange = renderPanel({ employment_type: 'internship' })

    await userEvent.selectOptions(screen.getByLabelText('Experience'), 'entry')

    expect(onChange).toHaveBeenCalledWith({
      employment_type: 'internship',
      experience_level: 'entry',
    })
  })
})
