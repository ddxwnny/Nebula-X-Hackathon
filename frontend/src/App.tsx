import { FormEvent, useState } from "react";

type SumResponse = { sum: number };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [firstNumber, setFirstNumber] = useState("");
  const [secondNumber, setSecondNumber] = useState("");
  const [sum, setSum] = useState<number | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const response = await fetch(`${API_URL}/api/sum`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_number: Number(firstNumber),
        second_number: Number(secondNumber),
      }),
    });
    const result: SumResponse = await response.json();
    setSum(result.sum);
  }

  return (
    <>
      <form onSubmit={handleSubmit}>
        <input
          aria-label="First number"
          type="number"
          value={firstNumber}
          onChange={(event) => setFirstNumber(event.target.value)}
        />
        <input
          aria-label="Second number"
          type="number"
          value={secondNumber}
          onChange={(event) => setSecondNumber(event.target.value)}
        />
        <button type="submit">Enter</button>
      </form>
      {sum !== null && <p>{sum}</p>}
    </>
  );
}
