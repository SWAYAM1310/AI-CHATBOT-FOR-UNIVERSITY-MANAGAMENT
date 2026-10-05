// The thought of the day on the student and faculty Home pages. The date picks it, so it changes
// on its own every midnight and everyone sees the same one that day; nothing
// here needs updating. Only quotes whose attribution is well established.

export interface Thought {
  text: string
  by: string
}

const THOUGHTS: Thought[] = [
  { text: 'Arise, awake, and stop not till the goal is reached.', by: 'Swami Vivekananda' },
  { text: 'The beautiful thing about learning is that nobody can take it away from you.', by: 'B. B. King' },
  { text: 'Excellence is a continuous process and not an accident.', by: 'A. P. J. Abdul Kalam' },
  { text: 'Simplicity is prerequisite for reliability.', by: 'Edsger W. Dijkstra' },
  { text: 'The important thing is not to stop questioning.', by: 'Albert Einstein' },
  { text: 'Education is the most powerful weapon which you can use to change the world.', by: 'Nelson Mandela' },
  { text: 'A journey of a thousand miles begins with a single step.', by: 'Laozi' },
  { text: 'Programs must be written for people to read, and only incidentally for machines to execute.', by: 'Harold Abelson and Gerald Jay Sussman' },
  { text: 'Knowing is not enough; we must apply. Willing is not enough; we must do.', by: 'Johann Wolfgang von Goethe' },
  { text: 'If you want to shine like a sun, first burn like a sun.', by: 'A. P. J. Abdul Kalam' },
  { text: 'The best way to predict the future is to invent it.', by: 'Alan Kay' },
  { text: 'Nothing in life is to be feared, it is only to be understood.', by: 'Marie Curie' },
  { text: 'If I have seen further it is by standing on the shoulders of giants.', by: 'Isaac Newton' },
  { text: 'Strength does not come from physical capacity. It comes from an indomitable will.', by: 'Mahatma Gandhi' },
  { text: 'Well begun is half done.', by: 'Aristotle' },
  { text: 'The purpose of computing is insight, not numbers.', by: 'Richard Hamming' },
  { text: 'Life is like riding a bicycle. To keep your balance, you must keep moving.', by: 'Albert Einstein' },
  { text: 'The highest education is that which does not merely give us information but makes our life in harmony with all existence.', by: 'Rabindranath Tagore' },
  { text: 'Any fool can write code that a computer can understand. Good programmers write code that humans can understand.', by: 'Martin Fowler' },
  { text: 'The function of education is to teach one to think intensively and to think critically.', by: 'Martin Luther King Jr.' },
  { text: 'Fall seven times, stand up eight.', by: 'Japanese proverb' },
  { text: 'Make it work, make it right, make it fast.', by: 'Kent Beck' },
  { text: 'The only way to do great work is to love what you do.', by: 'Steve Jobs' },
  { text: 'Pure mathematics is, in its way, the poetry of logical ideas.', by: 'Albert Einstein' },
  { text: 'You have to dream before your dreams can come true.', by: 'A. P. J. Abdul Kalam' },
  { text: 'Perfection is achieved, not when there is nothing more to add, but when there is nothing left to take away.', by: 'Antoine de Saint-Exupéry' },
  { text: 'Curiosity is the wick in the candle of learning.', by: 'William Arthur Ward' },
  { text: 'Debugging is twice as hard as writing the code in the first place.', by: 'Brian Kernighan' },
  { text: 'Take up one idea. Make that one idea your life; think of it, dream of it, live on that idea.', by: 'Swami Vivekananda' },
  { text: 'The more that you read, the more things you will know. The more that you learn, the more places you’ll go.', by: 'Dr. Seuss' },
  { text: 'Imagination is more important than knowledge.', by: 'Albert Einstein' },
  { text: 'Change is the end result of all true learning.', by: 'Leo Buscaglia' },
  { text: 'Simple things should be simple, complex things should be possible.', by: 'Alan Kay' },
  { text: 'Genius is one percent inspiration, ninety-nine percent perspiration.', by: 'Thomas Edison' },
  { text: 'I am always doing that which I cannot do, in order that I may learn how to do it.', by: 'Pablo Picasso' },
  { text: 'Education is the manifestation of the perfection already in man.', by: 'Swami Vivekananda' },
  { text: 'We are what we repeatedly do. Excellence, then, is not an act, but a habit.', by: 'Will Durant' },
  { text: 'Do what you can, with what you have, where you are.', by: 'Theodore Roosevelt' },
]

/** The thought for a YYYY-MM-DD date: the next one in the list each day, round and round. */
export function thoughtFor(iso: string): Thought {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const day = Math.floor(Date.UTC(y, m - 1, d) / 86_400_000)
  return THOUGHTS[day % THOUGHTS.length]
}
