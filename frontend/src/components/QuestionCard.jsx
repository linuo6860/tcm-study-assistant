export default function QuestionCard({ explanation }) {
  const archive = explanation.archive_chapter;
  const archiveText = `${archive.book_title} / ${archive.chapter_title} / ${archive.section_title}`;

  return (
    <article className="question-card">
      <section>
        <h3>【题目】</h3>
        <p>{explanation.question}</p>
      </section>

      <section>
        <h3>【答案】</h3>
        <p className="answer-text">{explanation.answer}</p>
      </section>

      <section>
        <h3>【教材依据】</h3>
        {explanation.textbook_basis.map((basis, index) => (
          <blockquote key={`${basis.section_title}-${index}`}>
            <strong>{basis.book_title} - {basis.chapter_title} - {basis.section_title}</strong>
            <span>{basis.quote}</span>
          </blockquote>
        ))}
      </section>

      <section>
        <h3>【为什么选这个】</h3>
        <p>{explanation.why_correct}</p>
      </section>

      <section>
        <h3>【为什么不选其他】</h3>
        {explanation.why_others.map((item) => (
          <p key={item.option}>
            <strong>{item.option}</strong>：{item.reason}
          </p>
        ))}
      </section>

      <section>
        <h3>【一句话记忆】</h3>
        <p className="mnemonic">{explanation.mnemonic}</p>
      </section>

      <section>
        <h3>【归档章节】</h3>
        <p>{archiveText}</p>
      </section>
    </article>
  );
}

