import Foundation

public enum TaskGroupKind: String, CaseIterable, Identifiable {
    case overdue = "Overdue"
    case today = "Today"
    case upcoming = "Upcoming"
    case unscheduled = "Unscheduled"
    case done = "Done"

    public var id: String { rawValue }
}

public enum TaskGrouper {
    public static func group(_ tasks: [TaskItem], today: Date = Date()) -> [TaskGroupKind: [TaskItem]] {
        let todayString = isoDateString(today)
        var groups = Dictionary(uniqueKeysWithValues: TaskGroupKind.allCases.map { ($0, [TaskItem]()) })

        for task in tasks {
            let kind = groupKind(for: task, todayString: todayString)
            groups[kind, default: []].append(task)
        }

        for kind in TaskGroupKind.allCases {
            groups[kind] = sorted(groups[kind] ?? [])
        }

        return groups
    }

    public static func groupKind(for task: TaskItem, todayString: String) -> TaskGroupKind {
        if task.isDone {
            return .done
        }

        guard let dueDate = task.dueDate, !dueDate.isEmpty else {
            return .unscheduled
        }

        if dueDate < todayString {
            return .overdue
        }

        if dueDate == todayString {
            return .today
        }

        return .upcoming
    }

    public static func isoDateString(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? .current
        let components = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", components.year ?? 0, components.month ?? 0, components.day ?? 0)
    }

    private static func sorted(_ tasks: [TaskItem]) -> [TaskItem] {
        tasks.sorted { left, right in
            switch (left.dueDate, right.dueDate) {
            case let (leftDue?, rightDue?) where leftDue != rightDue:
                return leftDue < rightDue
            case (nil, _?):
                return false
            case (_?, nil):
                return true
            default:
                return left.id < right.id
            }
        }
    }
}
