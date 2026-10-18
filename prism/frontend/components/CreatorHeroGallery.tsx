import Image from "next/image";
import Link from "next/link";
import styles from "./CreatorHeroGallery.module.css";

const portraits = [
  { name: "Ray Dalio", username: "ray_dalio", image: "/creators/ray-dalio.png", position: "ray" },
  { name: "Kara Swisher", username: "kara_swisher", image: "/creators/kara-swisher.png", position: "kara" },
  { name: "Andrew Yang", username: "andrew_yang", image: "/creators/andrew-yang.png", position: "andrew" },
  { name: "Scott Galloway", username: "scott_galloway", image: "/creators/scott-galloway.png", position: "scott" },
  { name: "Bill Gates", username: "bill_gates", image: "/creators/bill-gates.png", position: "bill" },
  { name: "Mark Cuban", username: "mark_cuban", image: "/creators/mark-cuban.png", position: "mark" },
] as const;

export function CreatorHeroGallery() {
  return (
    <div className={styles.gallery} role="group" aria-label="Explore creator profiles">
      <div className={styles.orbit} aria-hidden="true" />
      {portraits.map(({ name, username, image, position }) => (
        <Link
          key={username}
          href={`/users/${username}`}
          aria-label={`Explore ${name}'s profile`}
          title={name}
          className={`${styles.portrait} ${styles[position]}`}
        >
          <Image
            src={image}
            alt={`Illustrated portrait of ${name}`}
            fill
            sizes="(max-width: 760px) 35vw, 180px"
            className={styles.image}
            priority={position === "bill" || position === "mark" || position === "scott"}
          />
        </Link>
      ))}
    </div>
  );
}
