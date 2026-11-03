export type DemoChapter = { id: string; number: number; title: string; duration: string };
export type DemoManga = { id: string; title: string; author: string; genres: string[]; synopsis: string; chapters: DemoChapter[] };

// Fictional UI fixtures only. Replace when published catalog integration is approved.
const chapters = (titles: string[]): DemoChapter[] => titles.map((title, index) => ({
  id: `chapter-${index + 1}`, number: index + 1, title, duration: `${18 + index % 7}:${index % 2 ? "42" : "16"}`,
}));
export const manga: DemoManga[] = [
  { id: "azure", title: "The Azure Chronicle", author: "Yuna Aoki", genres: ["Fantasy", "Adventure"], synopsis: "Above a sea of clouds, a young cartographer discovers a forgotten map. With a skyship crew and a compass that points toward memories, she sets out to find the world everyone else has forgotten.", chapters: chapters(["A Map of the Uncharted Sky", "The Wind Remembers", "A Ship Without a Captain", "Islands in the Mist", "The Quiet Compass", "Beyond the Blue", "A Forgotten Harbor", "Letters from Below", "The Last Cartographer", "Where the Clouds End", "A Promise in the Sky", "Homeward"]) },
  { id: "lantern", title: "Echoes of the Lantern Town", author: "Ren Mori", genres: ["Fantasy", "Mystery"], synopsis: "In a town where lanterns keep the memories of the dead alive, a quiet girl can hear the echoes in their light. When one lantern goes dark, she follows its final whisper into a story the town has tried to forget.", chapters: chapters(["The Girl Who Hears Echoes", "Lanterns and Memories", "The Vanishing of the North Light", "A Name in the Rain", "The Keeper's Promise"]) },
  { id: "ramen", title: "Ramen Ronin", author: "Kai Sato", genres: ["Adventure", "Slice of life"], synopsis: "A wandering chef trades his sword for a soup ladle. Every town has a recipe, every customer has a story, and the perfect bowl is always one journey away.", chapters: chapters(["One Bowl, One Beginning", "The Midnight Kitchen", "A Taste of Home"]) },
  { id: "frost", title: "Frostbloom Academy", author: "Mei Harada", genres: ["Fantasy", "Mystery"], synopsis: "Spring never reaches this school in the mountains. A new student finds a flower growing through the ice, and a secret beneath its roots.", chapters: chapters(["The Winter Entrance", "Flowers Beneath the Ice", "The Locked Classroom", "First Thaw"]) },
  { id: "horizon", title: "Steel Horizon", author: "Akira Ito", genres: ["Sci-fi", "Adventure"], synopsis: "An apprentice mechanic intercepts a signal from an abandoned orbital city. Someone is still there, waiting for a train that stopped running decades ago.", chapters: chapters(["The Signal"]) },
  { id: "herbalist", title: "The Herbalist's Apprentice", author: "Hana Kudo", genres: ["Fantasy", "Slice of life"], synopsis: "At a tiny forest shop, medicine grows beside magic. A skeptical apprentice learns that healing sometimes starts with listening.", chapters: chapters(["A Shop at the Forest's Edge", "Bitter Roots", "A Remedy for Rain", "The Patient Oak"]) },
  { id: "kitsune", title: "My Roommate Is a Kitsune", author: "Sora Nishi", genres: ["Slice of life", "Fantasy"], synopsis: "The rent is affordable, the commute is short, and the new roommate has nine tails. Sharing an apartment has never been quite this complicated.", chapters: chapters(["The Spare Room", "House Rules", "Nine Tails, One Umbrella"]) },
  { id: "sketchbook", title: "A Sketchbook for the Stars We Left Behind", author: "Nao Fujita", genres: ["Sci-fi", "Mystery"], synopsis: "An illustrator aboard the last passenger ship draws planets she has never visited. When her sketches begin predicting their next destinations, she searches the ship's archive for the life she cannot remember.", chapters: chapters(["An Unfamiliar Constellation", "Portrait of a Planet", "The Archive", "A Page Torn Away", "The Stars Remember"]) },
  { id: "rain", title: "After the Rain", author: "Emi Tanaka", genres: ["Slice of life"], synopsis: "Two strangers restore an old neighborhood cinema, one rainy afternoon at a time.", chapters: chapters(["The Empty Cinema", "Opening Night"]) },
  { id: "moon", title: "Moonlit Express", author: "Riku Hoshi", genres: ["Fantasy", "Mystery"], synopsis: "A train arrives only when the moon is full. Its newest conductor must find the destination of a passenger with no ticket.", chapters: chapters(["Platform Zero", "The Sleepless Passenger", "Last Stop"]) },
];

// Explicit editorial ordering for the demo; these are not live popularity or personalized rankings.
export const browseShelves = {
  recent: [manga[0], manga[1], manga[8], manga[9], manga[2], manga[3], manga[4], manga[5], manga[6], manga[7]],
  top: [manga[1], manga[0], manga[4], manga[3], manga[9], manga[2], manga[7], manga[5], manga[6], manga[8]],
  picks: [manga[5], manga[7], manga[9], manga[6], manga[2], manga[8], manga[1], manga[4], manga[0], manga[3]],
};
