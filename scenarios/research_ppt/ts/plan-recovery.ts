/** 宿主保留失败计划并执行显式局部修复；复用原交付链，不增加Agent循环。 */
import { AdapterRejected, object, type Obj } from './delivery-adapter.js';
import { ExecutionPolicy, type ExecutionHost } from './execution-policy.js';
import { PendingPlanStore, type PendingFailure } from './pending-plan.js';

const failure = (error: unknown): PendingFailure => error instanceof AdapterRejected
  ? {code:error.code,message:error.message,details:error.details}
  : {code:'adapter_execution_failed',message:'执行未完成，详细信息只留私有日志。'};
const recoverable = new Set(['slide_count_mismatch','invalid_plan','invalid_arguments','invalid_image','backend_tool_failed']);
function reject(code:string,message:string,details:Obj={}):never {throw new AdapterRejected(code,message,details);}

export class PlanRecovery {
  constructor(private readonly store:PendingPlanStore|undefined, private readonly policy:ExecutionPolicy,
    private readonly host:ExecutionHost) {}
  async render(args:Obj):Promise<Obj|undefined> {
    if (this.policy.strategy!=='host_delivery') return undefined;
    if (Object.keys(args).length!==1 || !Object.hasOwn(args,'plan'))
      return reject('invalid_arguments','render_deck 只接受必填 plan 参数。',{field:'arguments',allowed_fields:['plan'],
        missing_fields:Object.hasOwn(args,'plan')?[]:['plan']});
    if (!this.store) return this.policy.dispatch(this.host,'render_deck',args);
    // 拦截整稿重交，包括进程重启；不通过新draft重置失败预算。
    const pending=await this.store.activePending();
    if (pending) reject('pending_plan_exists','已保存失败计划，请用局部修改恢复，不重新提交整稿。',{pending_plan:pending});
    try {
      const value=await this.policy.dispatch(this.host,'render_deck',args);
      if (value && value.delivered!==true) {
        const receipt=await this.store.capture(args.plan,{code:'validation_failed',message:'实际渲染验收未通过。',details:value});
        return {...value,pending_plan:receipt};
      }
      return value;
    } catch(error) {
      if (!(error instanceof AdapterRejected) || !recoverable.has(error.code) || !object(args.plan)) throw error;
      if (error.code==='backend_tool_failed' && (!object(error.details.backend_report)
        || !['invalid_plan','invalid_arguments','unsupported_statistics','text_overflow','table_overflow','chart_label_overflow','out_of_bounds','content_overlap'].includes(String(error.details.backend_report.error))))
        throw error;
      let receipt:Obj;
      try { receipt=await this.store.capture(args.plan,failure(error)); }
      catch(storageError) {
        // 无法安全保留的畸形输入仍返回原诊断；绝不掩盖权限/版本/存储异常。
        if (storageError instanceof AdapterRejected && storageError.code==='invalid_pending_plan') throw error;
        throw storageError;
      }
      throw new AdapterRejected(error.code,error.message,{...error.details,pending_plan:receipt,
        next_action:'只修复指出的页或字段；使用 repair_pending_plan，保留其它页面、来源和科学条件。'});
    }
  }
  async read(args:Obj):Promise<Obj> {
    await this.allowed('read_pending_plan',args);
    if (!this.store) return reject('output_permission_denied','草稿恢复需要原任务明确输出授权。');
    try { return await this.store.read(String(args.draft_id),String(args.version_sha256),args.pages as number[]); }
    catch(error) { return this.currentReceiptError(error); }
  }
  private async currentReceiptError(error:unknown):Promise<never> {
    if (!(error instanceof AdapterRejected) || !this.store ||
      !['invalid_pending_handle','invalid_pending_patch','invalid_pending_pages','pending_version_changed','no_changes'].includes(error.code)) throw error;
    // Help the model copy the current receipt; never substitute arguments or retry writes.
    const pending=await this.store.activePending();
    if (!pending) throw error;
    throw new AdapterRejected(error.code,error.message,{...error.details,pending_plan:pending,
      next_action:'上次调用没有执行修改。逐字复制此最新 draft_id/version_sha256，先读取明确失败页，再提交合法局部修改；不要猜句柄、重发整稿或重置任务。'});
  }
  private async allowed(name:string,args:Obj):Promise<void> {
    if (this.policy.strategy!=='host_delivery') await this.policy.dispatch(this.host,name,args);
    await this.host.guard();
  }
  async repair(args:Obj):Promise<Obj> {
    await this.allowed('repair_pending_plan',args);
    if (!this.store) return reject('output_permission_denied','草稿恢复需要原任务明确输出授权。');
    const {draft_id,version_sha256,...patch}=args;
    let patched:Obj;
    try { patched=await this.store.patch(String(draft_id),String(version_sha256),patch); }
    catch(error) { return this.currentReceiptError(error); }
    if (!object(patched.preflight) || patched.preflight.valid!==true)
      return {ok:false,code:'pending_preflight_failed',message:'局部修改已保留，尚有指出的计划错误；继续明确局部修复。',
        pending_plan:patched,automatic_retry:false};
    const attempt=await this.store.prepareAttempt(String(draft_id),String(patched.version_sha256));
    try {
      const value=await this.policy.dispatch(this.host,'repair_pending_plan',args,attempt.plan);
      if (!value) reject('execution_policy_tool_disabled','当前策略不支持局部恢复。');
      const receipt=await this.store.recordOutcome(String(draft_id),String(attempt.receipt.version_sha256),attempt.attempt_id,
        value.delivered===true ? {delivered:true} : {delivered:false,failure:{code:'validation_failed',message:'实际渲染验收未通过。',details:value}});
      return {...value,pending_plan:receipt,local_repair:{changed_pages:patched.changed_pages,
        deleted_pages:patched.deleted_pages,inserted_before_pages:patched.inserted_before_pages,
        changed_metadata:patched.changed_metadata},automatic_retry:false};
    } catch(error) {
      const receipt=await this.store.recordOutcome(String(draft_id),String(attempt.receipt.version_sha256),attempt.attempt_id,
        {delivered:false,failure:failure(error)});
      const original=failure(error);
      throw new AdapterRejected(original.code,original.message,{...original.details,pending_plan:receipt,
        next_action:'只修复新的错误位置；不要重新输出整稿。'});
    }
  }
}
