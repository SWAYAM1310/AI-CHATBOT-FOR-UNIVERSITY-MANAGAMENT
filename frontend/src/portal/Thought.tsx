import { thoughtFor } from './thoughts'

/** The thought of the day for a YYYY-MM-DD date, as it opens a Home page. */
export function ThoughtOfTheDay({ date }: { date: string }) {
  const thought = thoughtFor(date)
  return (
    <figure className="thought">
      <figcaption className="thought-label">Thought of the day</figcaption>
      <blockquote>
        <p>{thought.text}</p>
      </blockquote>
      <p className="thought-by">{thought.by}</p>
    </figure>
  )
}
