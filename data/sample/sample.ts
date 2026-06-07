// Sample TypeScript module used to exercise the tokenizer and data loader.

interface Greeter {
  greet(name: string): string;
}

interface Repository<T> {
  add(item: T): void;
  all(): readonly T[];
  find(predicate: (item: T) => boolean): T | undefined;
}

class Hello implements Greeter {
  private readonly prefix: string;

  constructor(prefix: string = "Hello") {
    this.prefix = prefix;
  }

  greet(name: string): string {
    return `${this.prefix}, ${name}!`;
  }
}

class InMemoryRepo<T> implements Repository<T> {
  private items: T[] = [];

  add(item: T): void {
    this.items.push(item);
  }

  all(): readonly T[] {
    return this.items.slice();
  }

  find(predicate: (item: T) => boolean): T | undefined {
    return this.items.find(predicate);
  }
}

type Person = { name: string; age: number };

function pluralize(word: string, count: number): string {
  return count === 1 ? word : `${word}s`;
}

async function loadPeople(path: string): Promise<Person[]> {
  const fs = await import("node:fs/promises");
  const raw = await fs.readFile(path, "utf8");
  const data: unknown = JSON.parse(raw);
  if (!Array.isArray(data)) {
    throw new TypeError(`expected an array at ${path}`);
  }
  return data as Person[];
}

const greeter = new Hello();
const people = new InMemoryRepo<Person>();
people.add({ name: "Alice", age: 30 });
people.add({ name: "Bob", age: 27 });

for (const p of people.all()) {
  console.log(greeter.greet(p.name));
}

const found = people.find((p) => p.age > 28);
if (found !== undefined) {
  console.log(`Oldest: ${found.name}`);
}

console.log(
  `Greeted ${people.all().length} ${pluralize("person", people.all().length)}.`,
);

export { Hello, InMemoryRepo, pluralize, loadPeople };
export type { Greeter, Repository, Person };
