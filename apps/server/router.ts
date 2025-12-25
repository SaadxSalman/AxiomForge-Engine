import { initTRPC } from '@trpc/server';
import { z } from 'zod';

const t = initTRPC.create();

export const appRouter = t.router({
  translate: t.procedure
    .input(z.object({ text: z.string(), targetLang: z.string() }))
    .query(async ({ input }) => {
      // Logic to call your Cultural Context Agent would go here
      return { response: `Translated ${input.text} to ${input.targetLang}` };
    }),
});

export type AppRouter = typeof appRouter;