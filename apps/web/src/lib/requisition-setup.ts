interface SetupRequisition {
  current_jd_version_id?: string | null;
  current_rubric_version_id?: string | null;
}
interface SetupRubric { id: string; status: string; jd_version_id: string }
type Blocker = 'unavailable' | 'missing_jd' | 'missing_rubric' | 'unapproved_rubric' | 'outdated_rubric';
interface RequisitionSetup {
  ready: boolean;
  action: 'setup' | 'reload' | 'open';
  blocker: Blocker | null;
  message: string;
}

/** Match the API's draft-to-open prerequisites using the current approved version,
 * independently of the rubric draft currently displayed in the editor. */
export function getRequisitionSetup(requisition: SetupRequisition | null, rubrics: SetupRubric[], unavailable = false): RequisitionSetup {
  const blocked = (blocker: Blocker, message: string): RequisitionSetup => ({
    ready: false, action: blocker === 'unavailable' ? 'reload' : 'setup', blocker, message,
  });
  if (unavailable || !requisition) return blocked('unavailable', 'Chưa xác minh được JD và tiêu chí. Làm mới trạng thái trước khi mở nhận hồ sơ.');
  if (!requisition.current_jd_version_id) return blocked('missing_jd', 'Chưa có JD. Vào JD & tiêu chí để nhập yêu cầu vị trí, tạo và duyệt rubric trước khi nhận CV.');
  if (!requisition.current_rubric_version_id) {
    if (rubrics.some(rubric => rubric.status === 'draft' && rubric.jd_version_id === requisition.current_jd_version_id)) {
      return blocked('unapproved_rubric', 'Rubric còn ở bản nháp. Vào JD & tiêu chí, kiểm tra tiêu chí và phê duyệt rubric trước khi mở nhận CV.');
    }
    return blocked('missing_rubric', 'Đã có JD nhưng chưa có rubric được duyệt. Vào JD & tiêu chí để tạo bộ tiêu chí, rà soát và phê duyệt.');
  }
  const current = rubrics.find(rubric => rubric.id === requisition.current_rubric_version_id);
  if (!current) return blocked('unavailable', 'Chưa tải được rubric hiện hành. Làm mới trạng thái trước khi mở nhận hồ sơ.');
  if (current.status !== 'approved') return blocked('unapproved_rubric', 'Rubric hiện hành chưa được duyệt. Vào JD & tiêu chí để rà soát và phê duyệt trước khi nhận CV.');
  if (current.jd_version_id !== requisition.current_jd_version_id) return blocked('outdated_rubric', 'JD đã thay đổi. Cần tạo và duyệt rubric theo JD hiện hành trước khi mở nhận CV.');
  return { ready: true, action: 'open', blocker: null, message: 'JD và rubric đã sẵn sàng. Mở nhận hồ sơ để tải CV vào đợt này.' };
}
