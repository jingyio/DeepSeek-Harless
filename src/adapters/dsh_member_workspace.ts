/** Bootstrap one durable workspace inside each member's isolated DSH home. */
export const name = 'harless-member-workspace';
export const inject = ['workspaceRegistry'];

export async function apply(ctx: any) {
  await ctx.workspaceRegistry.create('/user/workspace', '我的工作区');
}
