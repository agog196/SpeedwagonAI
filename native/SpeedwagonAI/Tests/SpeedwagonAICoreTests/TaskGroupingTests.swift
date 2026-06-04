import XCTest
@testable import SpeedwagonAICore

final class TaskGroupingTests: XCTestCase {
    func testGroupsTasksByOperationalBucket() {
        let tasks = [
            makeTask(id: 1, dueDate: "2026-05-30", status: "open"),
            makeTask(id: 2, dueDate: "2026-05-31", status: "open"),
            makeTask(id: 3, dueDate: "2026-06-01", status: "open"),
            makeTask(id: 4, dueDate: nil, status: "open"),
            makeTask(id: 5, dueDate: "2026-05-29", status: "done")
        ]
        let groups = TaskGrouper.group(tasks, today: date("2026-05-31"))

        XCTAssertEqual(groups[.overdue]?.map(\.id), [1])
        XCTAssertEqual(groups[.today]?.map(\.id), [2])
        XCTAssertEqual(groups[.upcoming]?.map(\.id), [3])
        XCTAssertEqual(groups[.unscheduled]?.map(\.id), [4])
        XCTAssertEqual(groups[.done]?.map(\.id), [5])
    }

    func testSortsDatedTasksBeforeUnscheduledWithinGroups() {
        let tasks = [
            makeTask(id: 8, dueDate: "2026-06-03", status: "open"),
            makeTask(id: 7, dueDate: "2026-06-01", status: "open")
        ]
        let groups = TaskGrouper.group(tasks, today: date("2026-05-31"))

        XCTAssertEqual(groups[.upcoming]?.map(\.id), [7, 8])
    }

    private func makeTask(id: Int, dueDate: String?, status: String) -> TaskItem {
        TaskItem(
            id: id,
            text: "Task \(id)",
            owner: nil,
            dueDate: dueDate,
            status: status,
            source: "manual",
            kind: "manual",
            sourceMeetingId: nil,
            meetingId: nil,
            meetingTitle: nil,
            reminderSuggestion: nil,
            isOverdue: nil,
            completedAt: nil,
            createdAt: nil,
            updatedAt: nil
        )
    }

    private func date(_ value: String) -> Date {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)!
    }
}
