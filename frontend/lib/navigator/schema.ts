import { z } from 'zod';
export const sourceSchema = z.object({ id:z.string(), title:z.string(), url:z.string().url().refine(v=>/^https?:/.test(v)), excerpt:z.string(), retrievedAt:z.string() });
export const factSchema = z.object({text:z.string(),sourceIds:z.array(z.string())});
export const resultSchema = z.object({id:z.string(),name:z.string(),kind:z.enum(['Person','Research group','Service']),institution:z.string(),role:factSchema.nullable(),unit:factSchema.nullable(),expertise:z.array(factSchema),projects:z.array(factSchema),services:z.array(factSchema),reason:factSchema,contact:z.object({label:z.string(),url:z.string().url().refine(v=>/^(https?:|mailto:)/.test(v))}).nullable(),sources:z.array(sourceSchema)});
export type Result = z.infer<typeof resultSchema>;
export const eventSchema = z.discriminatedUnion('type',[
 z.object({type:z.literal('status'),message:z.string()}),
 z.object({type:z.literal('result'),result:resultSchema}),
 z.object({type:z.literal('complete'),orderedIds:z.array(z.string())}),
 z.object({type:z.literal('error'),message:z.string()})
]);
export type SearchEvent=z.infer<typeof eventSchema>;
