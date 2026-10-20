import { x } from "./x";

export function exported(a: number): number {
  return a + 1;
}

const notExported = (n: number) => {
  const inner = () => n * 2;
  return inner();
};

export class Service {
  private cache = new Map<string, number>();
  handler = async (id: string) => {
    return this.cache.get(id);
  };
  static create(): Service {
    return new Service();
  }
  get size(): number {
    return this.cache.size;
  }
  run(job: string): void {
    const cb = () => job.length;
    cb();
  }
}

export const config = {
  retries: 3,
  fetchAll() {
    return [1, 2, 3];
  },
  parse: (s: string) => s.trim(),
};

function nested() {
  function deeper() {
    return 1;
  }
  return deeper();
}

function overload(a: string): string;
function overload(a: number): number;
function overload(a: any): any {
  return a;
}

export interface Shape {
  area(): number;
}

export type Id = string | number;

export namespace Ns {
  export function inNs() {
    return 1;
  }
}

[1, 2].forEach((v) => {
  console.log(v);
});

@Injectable()
export class Decorated {
  @Input() label = "x";
  @Log()
  decoratedMethod() {
    return 1;
  }
}
